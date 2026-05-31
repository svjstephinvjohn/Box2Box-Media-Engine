# Football App — AWS Serverless Architecture

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AWS Free-Tier Serverless Architecture               │
└─────────────────────────────────────────────────────────────────────────────┘

EventBridge (cron every 30 min)
        │
        ▼
┌──────────────────────┐
│  News Ingestion      │  Lambda  512MB / 3min
│  Lambda              │  ─ Fetch RSS feeds (8 sources)
│                      │  ─ OpenAI text-embedding-3-small
│                      │  ─ Store in DynamoDB + TTL 72h
│                      │  ─ Detect trends → DynamoDB
└──────────┬───────────┘
           │ StartExecution
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  Step Functions Express Workflow                          │
│                  (football-app-content-pipeline)                         │
│                                                                          │
│  ┌─────────────────┐                                                     │
│  │ Content         │  Lambda  256MB / 30s                                │
│  │ Selection       │  ─ Read top trends (DynamoDB)                       │
│  │                 │  ─ Deduplicate (skip posted in 24h)                 │
│  │                 │  ─ Priority scoring:                                │
│  │                 │      Breaking +30  World Cup +20  Transfer +10      │
│  │                 │  ─ Check daily post limit (default: 5)              │
│  └────────┬────────┘                                                     │
│           │ content_found=true                                           │
│           ▼                                                              │
│  ┌─────────────────┐                                                     │
│  │ Caption         │  Lambda  256MB / 60s                                │
│  │ Generation      │  ─ DynamoDB RAG retrieval                          │
│  │                 │  ─ Cosine similarity in Lambda (no OpenSearch)      │
│  │                 │  ─ OpenAI GPT-4o caption                           │
│  └────────┬────────┘                                                     │
│           ▼                                                              │
│  ┌─────────────────┐                                                     │
│  │ Image Prompt    │  Lambda  128MB / 30s                                │
│  │ Generation      │  ─ GPT-4o generates DALL-E prompt                  │
│  └────────┬────────┘                                                     │
│           ▼                                                              │
│  ┌─────────────────┐                                                     │
│  │ Image           │  Lambda  512MB / 2min                               │
│  │ Generation      │  ─ DALL-E 3 (1024×1024)                            │
│  │                 │  ─ Upload PNG → S3 (private + presigned URL)        │
│  │                 │  ─ Create post record → DynamoDB                    │
│  └────────┬────────┘                                                     │
│           │                                                              │
│    ┌──────┴──────┐                                                       │
│    │ approval    │                                                       │
│    │ mode?       │                                                       │
│    └──┬─────┬───┘                                                       │
│       │auto │approval_required                                          │
│       │     ▼                                                           │
│       │  ┌─────────────────┐                                            │
│       │  │ Approval        │  WaitForTaskToken                          │
│       │  │ Notifier        │  ─ SNS email with preview link             │
│       │  │                 │  ─ Approve/Reject URLs                     │
│       │  │                 │  ─ 24h expiry                              │
│       │  └────────┬────────┘                                            │
│       │           │ approved                                            │
│       └─────┬─────┘                                                     │
│             ▼                                                           │
│  ┌─────────────────┐                                                     │
│  │ Instagram       │  Lambda  256MB / 60s                                │
│  │ Publisher       │  ─ Presigned URL → Meta Graph API                  │
│  │                 │  ─ Create container → Publish                      │
│  │                 │  ─ Update DynamoDB publishing log                  │
│  └─────────────────┘                                                     │
└──────────────────────────────────────────────────────────────────────────┘

EventBridge (every 45 days)
        │
        ▼
┌──────────────────────┐
│  Token Refresh       │  Lambda  128MB / 30s
│  Lambda              │  ─ Refresh Instagram long-lived token
│                      │  ─ Update Secrets Manager
└──────────────────────┘
```

---

## RAG Implementation (DynamoDB, No OpenSearch)

OpenSearch Serverless costs ~$350/month — far outside Free Tier.

This app implements RAG entirely within Lambda + DynamoDB:

```
Article ingest:
  title + summary → OpenAI text-embedding-3-small → 1536-dim vector
  → stored in DynamoDB as list[Decimal]  (72h TTL)

Retrieval at caption time:
  query string → OpenAI embedding → query vector
  → DynamoDB Scan (last 48h, max 200 articles)
  → cosine similarity computed in Python (in Lambda memory)
  → return top-5 most similar articles as context block
  → inject into GPT-4o system prompt
```

**Cost**: text-embedding-3-small is $0.02 per 1M tokens.
~1,000 articles/day × ~100 tokens avg = 100K tokens/day ≈ $0.002/day ≈ $0.06/month.

---

## DynamoDB Table Designs

### `football-news-articles`
| Key | Type | Notes |
|-----|------|-------|
| `article_id` (PK) | String | SHA-256 of article URL |
| `ingested_at` (SK) | String | ISO timestamp |
| `title` | String | Article title |
| `summary` | String | Article summary |
| `source_name` | String | e.g. "BBC Sport Football" |
| `link` | String | Original URL |
| `embedding` | List[Decimal] | 1536-dim vector |
| `is_breaking` | Boolean | Content flag |
| `is_transfer` | Boolean | Content flag |
| `is_world_cup` | Boolean | Content flag |
| `content_score` | Number | Priority score |
| `expires_at` | Number | Unix epoch (TTL, 72h) |

GSI: `source-date-index` (source_name, ingested_at)

### `football-generated-posts`
| Key | Type | Notes |
|-----|------|-------|
| `post_id` (PK) | String | UUID |
| `created_at` (SK) | String | ISO timestamp |
| `post_type` | String | breaking_news / transfer / match_result |
| `caption` | String | Generated Instagram caption |
| `image_s3_key` | String | S3 object key |
| `source_topic` | String | Trend topic (for dedup) |
| `status` | String | pending / published / rejected |
| `approval_mode` | String | auto / approval_required |
| `expires_at` | Number | Unix epoch (TTL, 30 days) |

GSI: `status-index` (status, created_at)

### `football-publishing-log`
| Key | Type | Notes |
|-----|------|-------|
| `post_id` (PK) | String | UUID |
| `published_at` (SK) | String | ISO timestamp |
| `instagram_media_id` | String | Meta media ID |
| `status` | String | success / failed |
| `error_message` | String | Error details |

### `football-trends`
| Key | Type | Notes |
|-----|------|-------|
| `trend_id` (PK) | String | UUID |
| `detected_at` (SK) | String | ISO timestamp |
| `topic` | String | Trend headline |
| `keywords` | List | Matched keywords |
| `virality_score` | Decimal | 0–10 |
| `priority_score` | Decimal | Virality + content bonuses |
| `is_breaking` | Boolean | |
| `is_transfer` | Boolean | |
| `is_world_cup` | Boolean | |
| `draft_post_generated` | Boolean | Dedup flag |
| `expires_at` | Number | Unix epoch (TTL, 24h) |

---

## Lambda Functions Summary

| Function | Memory | Timeout | Trigger |
|----------|--------|---------|---------|
| `news_ingestion` | 512 MB | 3 min | EventBridge every 30 min |
| `content_selection` | 256 MB | 30 s | Step Functions |
| `caption_generation` | 256 MB | 60 s | Step Functions |
| `image_prompt` | 128 MB | 30 s | Step Functions |
| `image_generation` | 512 MB | 2 min | Step Functions |
| `approval_notifier` | 128 MB | 30 s | Step Functions (WaitForTaskToken) |
| `instagram_publisher` | 256 MB | 60 s | Step Functions |
| `token_refresh` | 128 MB | 30 s | EventBridge every 45 days |

---

## AWS Free Tier Cost Estimate

| Service | Free Tier | Estimated Monthly Usage | Cost |
|---------|-----------|------------------------|------|
| Lambda | 1M req + 400K GB-s | ~1,500 req + ~20K GB-s | **$0** |
| DynamoDB | 25 WCU/RCU, 25 GB | < 1 GB, burst reads | **$0** |
| S3 | 5 GB, 20K GET, 2K PUT | < 100 MB, ~300 PUT | **$0** |
| EventBridge | 14M events/month | ~1,500 events | **$0** |
| Step Functions Express | 4K state transitions | ~700 transitions | **$0** |
| CloudWatch Logs | 5 GB/month | < 1 GB | **$0** |
| Secrets Manager | — NOT free tier — | 3 secrets | **~$1.20/mo** |
| OpenAI Embeddings | — | ~100K tokens/day | **~$0.06/mo** |
| OpenAI GPT-4o | — | ~50 captions/month | **~$0.50/mo** |
| OpenAI DALL-E 3 | — | ~100 images/month | **~$4.00/mo** |
| **Total** | | | **~$5.76/mo** |

> **Tip**: To eliminate Secrets Manager cost, replace with Lambda environment
> variables for a dev/capstone setup (trade-off: less secure).

---

## Secrets Setup (post-deploy)

After `cdk deploy`, populate the placeholder secrets:

```bash
# OpenAI
aws secretsmanager put-secret-value \
  --secret-id football-app/openai \
  --secret-string '{"api_key": "sk-..."}'

# Meta / Instagram
aws secretsmanager put-secret-value \
  --secret-id football-app/meta \
  --secret-string '{
    "app_id": "...",
    "app_secret": "...",
    "access_token": "EAAG...",
    "account_id": "..."
  }'

# API-Football (RapidAPI)
aws secretsmanager put-secret-value \
  --secret-id football-app/api-football \
  --secret-string '{"api_key": "..."}'
```

---

## Deployment

### Prerequisites
```bash
npm install -g aws-cdk
pip install -r infrastructure/requirements.txt
pip install -r requirements-lambda.txt
```

### Bootstrap + Deploy
```bash
cd infrastructure
cdk bootstrap aws://YOUR_ACCOUNT_ID/us-east-1
cdk deploy --all --require-approval never
```

### Manual approval mode
To switch to human-approval mode, update the Lambda environment variable:
```bash
aws lambda update-function-configuration \
  --function-name football-app-contentselection \
  --environment "Variables={APPROVAL_MODE=approval_required,...}"
```

---

## Folder Structure

```
Football_App/
├── app/                          # Core app services (reused by Lambdas)
│   ├── core/config.py            # Updated: AWS + legacy settings
│   └── services/
│       └── rag/
│           └── dynamodb_retriever.py  # NEW: DynamoDB RAG (replaces ChromaDB)
├── lambdas/                      # Lambda function code
│   ├── shared/                   # Lambda Layer (shared utilities)
│   │   ├── secrets.py            # Secrets Manager client
│   │   ├── dynamodb_client.py    # DynamoDB table accessors
│   │   ├── rag.py                # DynamoDB cosine-similarity RAG
│   │   └── openai_client.py      # OpenAI (chat + embeddings + DALL-E)
│   ├── news_ingestion/handler.py
│   ├── content_selection/handler.py
│   ├── caption_generation/handler.py
│   ├── image_prompt/handler.py
│   ├── image_generation/handler.py
│   ├── approval_notifier/handler.py
│   ├── instagram_publisher/handler.py
│   └── token_refresh/handler.py
├── infrastructure/               # AWS CDK (Python)
│   ├── app.py                    # CDK app entry point
│   ├── cdk.json                  # CDK config
│   ├── requirements.txt          # CDK deps
│   └── stacks/
│       ├── secrets_stack.py      # Secrets Manager
│       ├── storage_stack.py      # DynamoDB + S3
│       ├── lambda_stack.py       # All Lambda functions
│       ├── step_functions_stack.py
│       └── eventbridge_stack.py
├── step_functions/
│   └── workflow.json             # Step Functions ASL definition
├── requirements.txt              # Updated (boto3, no celery/mongo/chromadb)
└── requirements-lambda.txt       # Lambda bundle deps
```

---

## Error Handling & Retry Strategy

| Layer | Strategy |
|-------|----------|
| Lambda | Built-in retry on `Lambda.ServiceException` (up to 3× with exponential backoff) |
| Step Functions | Per-state `Retry` blocks; `Catch` routes failures to `PipelineFailed` terminal state |
| News ingest | Individual article failures are caught and logged; pipeline continues |
| Instagram publish | 3× retry with 30s interval; failure logged to DynamoDB publishing log |
| Token expiry | Approval WaitForTaskToken has 24h heartbeat timeout → `ApprovalTimeout` success state |

---

## Monitoring

All Lambda functions log to **CloudWatch Logs** (`/aws/lambda/football-app-*`).
Step Functions execution history is logged to `/football-app/step-functions/content-pipeline`.

Key metrics to watch in CloudWatch:
- `Lambda/Errors` — any function error rate > 0
- `Lambda/Duration` — image generation should stay < 90s
- `States/ExecutionsFailed` — failed pipeline runs
- Custom metric: `football_app/posts_published_today` (emit from publisher Lambda)
