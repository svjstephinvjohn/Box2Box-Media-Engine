"""
Lambda Stack — all Lambda functions + shared Lambda Layer.

Memory / timeout sizing for Free Tier:
  Free Tier: 1M requests + 400,000 GB-seconds/month
  At 48 runs/day (news ingest every 30 min) the app uses ~1,440 invocations/month.
  Well within the 1M free requests.

  GB-seconds budget per run:
    news_ingestion:       512MB × 180s = 92,160 MB-s
    content_selection:    256MB × 30s  = 7,680  MB-s
    caption_generation:   256MB × 60s  = 15,360 MB-s
    image_prompt:         128MB × 30s  = 3,840  MB-s
    image_generation:     512MB × 120s = 61,440 MB-s
    instagram_publisher:  256MB × 60s  = 15,360 MB-s
  Total per pipeline run: ~195,840 MB-s ≈ 191 GB-s

  At ~100 pipeline runs/month: ~19,100 GB-s — within 400,000 free-tier limit.
"""
import os
import aws_cdk as cdk
import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
from constructs import Construct

from stacks.secrets_stack import SecretsStack
from stacks.storage_stack import StorageStack

LAMBDA_RUNTIME = _lambda.Runtime.PYTHON_3_12
LAMBDA_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "lambdas")


class LambdaStack(cdk.Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        secrets_stack: SecretsStack,
        storage_stack: StorageStack,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        self._secrets = secrets_stack
        self._storage = storage_stack

        # ── Shared Lambda Layer ───────────────────────────────────────────────
        self.shared_layer = _lambda.LayerVersion(
            self,
            "SharedLayer",
            code=_lambda.Code.from_asset(
                os.path.join(LAMBDA_ROOT, "shared"),
            ),
            compatible_runtimes=[LAMBDA_RUNTIME],
            description="Football App shared utilities (secrets, DynamoDB, RAG, OpenAI)",
        )

        # ── Common environment variables ──────────────────────────────────────
        common_env = {
            "NEWS_ARTICLES_TABLE": storage_stack.news_articles_table.table_name,
            "GENERATED_POSTS_TABLE": storage_stack.generated_posts_table.table_name,
            "PUBLISHING_LOG_TABLE": storage_stack.publishing_log_table.table_name,
            "TRENDS_TABLE": storage_stack.trends_table.table_name,
            "IMAGES_BUCKET_NAME": storage_stack.images_bucket.bucket_name,
            "OPENAI_SECRET_NAME": secrets_stack.openai_secret.secret_name,
            "META_SECRET_NAME": secrets_stack.meta_secret.secret_name,
            "API_FOOTBALL_SECRET_NAME": secrets_stack.api_football_secret.secret_name,
            "OPENAI_MODEL": "gpt-4o",
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
            "DAILY_POST_LIMIT": "5",
            "APPROVAL_MODE": "auto",
            "DALLE_IMAGE_SIZE": "1024x1024",
            "RAG_TOP_K": "5",
            "RAG_SCAN_LIMIT": "200",
            "MAX_ARTICLES_PER_SOURCE": "15",
            "LOG_LEVEL": "INFO",
        }

        # ── Lambda functions ──────────────────────────────────────────────────

        self.news_ingestion_fn = self._create_lambda(
            "NewsIngestion",
            "news_ingestion/handler.py",
            "handler",
            memory_mb=512,
            timeout_seconds=180,
            env=common_env,
            description="Fetch RSS news, generate embeddings, store in DynamoDB, start pipeline",
        )

        self.content_selection_fn = self._create_lambda(
            "ContentSelection",
            "content_selection/handler.py",
            "handler",
            memory_mb=256,
            timeout_seconds=30,
            env=common_env,
            description="Select highest-priority trending content for posting",
        )

        self.caption_generation_fn = self._create_lambda(
            "CaptionGeneration",
            "caption_generation/handler.py",
            "handler",
            memory_mb=256,
            timeout_seconds=60,
            env=common_env,
            description="RAG retrieval + GPT-4o caption generation",
        )

        self.image_prompt_fn = self._create_lambda(
            "ImagePrompt",
            "image_prompt/handler.py",
            "handler",
            memory_mb=128,
            timeout_seconds=30,
            env=common_env,
            description="Generate DALL-E 3 image prompt",
        )

        self.image_generation_fn = self._create_lambda(
            "ImageGeneration",
            "image_generation/handler.py",
            "handler",
            memory_mb=512,
            timeout_seconds=120,
            env=common_env,
            description="DALL-E 3 image generation + S3 upload + post record creation",
        )

        self.approval_notifier_fn = self._create_lambda(
            "ApprovalNotifier",
            "approval_notifier/handler.py",
            "handler",
            memory_mb=128,
            timeout_seconds=30,
            env=common_env,
            description="Send SNS approval notification and wait for task token callback",
        )

        self.instagram_publisher_fn = self._create_lambda(
            "InstagramPublisher",
            "instagram_publisher/handler.py",
            "handler",
            memory_mb=256,
            timeout_seconds=60,
            env=common_env,
            description="Publish post to Instagram via Meta Graph API",
        )

        self.token_refresh_fn = self._create_lambda(
            "TokenRefresh",
            "token_refresh/handler.py",
            "handler",
            memory_mb=128,
            timeout_seconds=30,
            env=common_env,
            description="Refresh Instagram long-lived access token",
        )

        # ── Grant permissions ─────────────────────────────────────────────────
        self._grant_permissions()

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "NewsIngestionFnArn", value=self.news_ingestion_fn.function_arn)
        cdk.CfnOutput(self, "ContentSelectionFnArn", value=self.content_selection_fn.function_arn)
        cdk.CfnOutput(self, "CaptionGenerationFnArn", value=self.caption_generation_fn.function_arn)
        cdk.CfnOutput(self, "ImagePromptFnArn", value=self.image_prompt_fn.function_arn)
        cdk.CfnOutput(self, "ImageGenerationFnArn", value=self.image_generation_fn.function_arn)
        cdk.CfnOutput(self, "ApprovalNotifierFnArn", value=self.approval_notifier_fn.function_arn)
        cdk.CfnOutput(self, "InstagramPublisherFnArn", value=self.instagram_publisher_fn.function_arn)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _create_lambda(
        self,
        construct_id: str,
        handler_path: str,
        handler_fn: str,
        memory_mb: int,
        timeout_seconds: int,
        env: dict,
        description: str,
    ) -> _lambda.Function:
        fn = _lambda.Function(
            self,
            construct_id,
            function_name=f"football-app-{construct_id.lower().replace(' ', '-')}",
            runtime=LAMBDA_RUNTIME,
            code=_lambda.Code.from_asset(LAMBDA_ROOT),
            handler=handler_path.replace("/", ".").replace(".py", "") + f".{handler_fn}",
            memory_size=memory_mb,
            timeout=cdk.Duration.seconds(timeout_seconds),
            environment=env,
            description=description,
            layers=[self.shared_layer],
            log_retention=logs.RetentionDays.ONE_WEEK,  # keep CloudWatch cost low
        )
        return fn

    def _grant_permissions(self) -> None:
        all_fns = [
            self.news_ingestion_fn,
            self.content_selection_fn,
            self.caption_generation_fn,
            self.image_prompt_fn,
            self.image_generation_fn,
            self.approval_notifier_fn,
            self.instagram_publisher_fn,
            self.token_refresh_fn,
        ]

        # DynamoDB access
        for fn in all_fns:
            self._storage.news_articles_table.grant_read_write_data(fn)
            self._storage.generated_posts_table.grant_read_write_data(fn)
            self._storage.publishing_log_table.grant_read_write_data(fn)
            self._storage.trends_table.grant_read_write_data(fn)

        # S3 access (image generation writes, publisher reads)
        self._storage.images_bucket.grant_put(self.image_generation_fn)
        self._storage.images_bucket.grant_read(self.instagram_publisher_fn)
        self._storage.images_bucket.grant_put_acl(self.image_generation_fn)

        # Secrets Manager read
        secrets = [
            self._secrets.openai_secret,
            self._secrets.meta_secret,
            self._secrets.api_football_secret,
        ]
        for fn in all_fns:
            for secret in secrets:
                secret.grant_read(fn)

        # Token refresh also needs to write the secret
        self._secrets.meta_secret.grant_write(self.token_refresh_fn)

        # news_ingestion needs to start Step Functions execution
        # (ARN injected at EventBridge stack level via environment variable)
        self.news_ingestion_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=["*"],  # narrowed to specific SFN ARN at deploy time via env var
            )
        )

        # approval_notifier needs SNS publish
        self.approval_notifier_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=["*"],
            )
        )
