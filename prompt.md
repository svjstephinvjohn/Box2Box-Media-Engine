# PROJECT: AI-Assisted Instagram Football Media Automation Platform (Human-in-the-Loop)

---

## IMPLEMENTATION STATUS (Last updated: 2026-05-25)

### ✅ BASELINED (Implemented in base project)

| # | Feature | Files |
|---|---------|-------|
| 1 | Project scaffold & folder structure | `app/`, `configs/`, `tests/` |
| 2 | Core configuration (env-based) | `app/core/config.py` |
| 3 | FastAPI app entrypoint | `app/main.py` |
| 4 | MongoDB async connection (Motor) | `app/core/database.py` |
| 5 | Redis async connection | `app/core/redis.py` |
| 6 | Celery app setup | `app/core/celery_app.py` |
| 7 | Structured logging (structlog) | `app/utils/logging.py` |
| 8 | Retry decorator (tenacity) | `app/utils/retry.py` |
| 9 | MongoDB document models | `app/models/` (fixture, post, story, trend, publishing_log) |
| 10 | Pydantic API schemas | `app/schemas/` (post, story, trend) |
| 11 | Repository pattern (base + all collections) | `app/repositories/` |
| 12 | Football Data Service (API-Football) | `app/services/football/` (api_client, fixtures, standings, transfers, news) |
| 13 | AI Caption Generation (OpenAI GPT-4o) | `app/services/ai/` (openai_client, caption_generator, prompt templates) |
| 14 | Graphic Rendering Engine (Playwright + Jinja2) | `app/media/renderers/playwright_renderer.py` |
| 15 | HTML graphic templates (posts + stories) | `app/media/templates/` (match_result, transfer, breaking_news, goal_alert, kickoff, fulltime) |
| 16 | Instagram Graph API integration | `app/integrations/instagram/` (api_client, publisher) |
| 17 | Celery workers (live scores, trends, auto-publish) | `app/workers/tasks.py` |
| 18 | Celery Beat scheduler (1min/5min/15min jobs) | `app/workers/beat_schedule.py` |
| 19 | Trend detection engine (RSS-based) | `app/services/trends/detector.py` |
| 20 | FastAPI routers (posts, stories, news, trends, admin, instagram) | `app/api/routers/` |
| 21 | Approval workflow endpoints (approve/reject/publish) | `app/api/routers/posts.py` |
| 22 | Admin dashboard summary endpoint | `app/api/routers/admin.py` |
| 23 | Docker & Docker Compose (backend, worker, beat, redis, mongo) | `Dockerfile`, `docker-compose.yml` |
| 24 | Branding config system | `configs/branding/default.json`, `epl_theme.json` |
| 25 | Environment config template | `.env.example` |
| 26 | Basic test scaffold | `tests/test_main.py` |

---

### 🔲 TODO (Not yet implemented)

| Priority | Feature | Notes |
|----------|---------|-------|
| HIGH | Publishing logs to MongoDB | Track every publish attempt with retry metadata |
| HIGH | Instagram OAuth token refresh flow | `app/integrations/instagram/auth.py` — long-lived token renewal |
| HIGH | Story auto-generation from live fixtures | Worker task to create kickoff/goal/fulltime stories automatically |
| HIGH | Match event → graphic pipeline | Wire live score sync to auto-trigger `generate_match_result_post` on FT status |
| HIGH | Admin UI / dashboard frontend | React or simple HTML dashboard for editorial review & approval |
| MEDIUM | Standings graphic template | `app/media/templates/posts/standings.html` |
| MEDIUM | Player stat card template | `app/media/templates/posts/player_stat.html` |
| MEDIUM | Matchday poster template | `app/media/templates/posts/matchday.html` |
| MEDIUM | Transfer news story template | `app/media/templates/stories/transfer.html` |
| MEDIUM | Branding config injection into renderers | Load `default.json` / `epl_theme.json` dynamically into HTML templates |
| MEDIUM | Multi-league fixture sync scheduling | Beat job to sync EPL, UCL, ISL fixtures daily |
| MEDIUM | Post scheduling (scheduled_at publish) | Worker that checks `scheduled_at` and publishes when due |
| MEDIUM | Analytics tracking (engagement metrics) | Post-publish analytics via Instagram Graph API insights |
| MEDIUM | Comprehensive test coverage | Unit tests for services, repositories, and renderers |
| LOW | Reddit trend source integration | Add Reddit football discussions to `TrendDetector` |
| LOW | Multilingual caption generation | Malayalam, Tamil, Hindi prompt variants in `caption_generator.py` |
| LOW | Multi-account Instagram support | Abstract account ID into per-account config |
| LOW | Telegram / WhatsApp Channels publishing | Future publisher integrations in `app/integrations/` |
| LOW | Celery Flower monitoring setup | Add Flower service to `docker-compose.yml` |
| LOW | YouTube Shorts / Reels pipeline stub | Placeholder architecture for future video automation |

---


## Objective

Build a production-grade Python backend system that powers an Instagram football media brand focused on Indian football fans.

The platform should NOT be a fully autonomous AI spam system.

Instead, it should operate like a modern football media company:
- automated data ingestion,
- AI-assisted content generation,
- auto-generated graphics,
- trend detection,
- approval workflows,
- scheduled publishing,
- and editorial oversight.

The system should help a small team scale like a large football media page such as:
- 433
- Goal
- OneFootball
- Troll Football

INITIAL SCOPE:
- Instagram feed posts
- Instagram stories
- Match graphics
- Breaking news graphics
- AI-generated captions
- Story automation
- Admin approval dashboard

DO NOT IMPLEMENT:
- reels/video generation
- engagement bots
- fake interaction automation
- auto-commenting
- auto-follow systems

The architecture must remain extensible for future reel/video automation.

---

# PRODUCT VISION

Create a football media engine optimized for:
- Indian football fans
- EPL audience
- UCL audience
- Transfer news
- Fast breaking updates
- Localized football culture

The platform should prioritize:
- speed,
- consistency,
- branding,
- editorial quality,
- and automation-assisted scaling.

---

# TARGET AUDIENCE

Primary:
- Indian football fans aged 16–35

Secondary:
- EPL fans
- UCL fans
- Kerala football audience
- Fantasy football audience

Future localization support:
- English
- Malayalam
- Tamil
- Hindi

---

# CONTENT TYPES

## Feed Posts
- Match result cards
- Transfer announcements
- Breaking news graphics
- League table snapshots
- Player stat cards
- Matchday posters

## Stories
- Goal alerts
- Match kickoff reminders
- Full-time scores
- Poll-style graphics
- Breaking updates

---

# IMPORTANT PRODUCT PRINCIPLES

## 1. Human-in-the-Loop Publishing

Automation should PREPARE content.

Humans should APPROVE content.

Workflow:
Football event detected
    ->
AI generates caption
    ->
Graphic generated
    ->
Editor reviews
    ->
Publish to Instagram

Only low-risk story updates may auto-publish.

---

# 2. Template-Based Media System

The platform should use reusable templates.

Example:
- score template
- transfer template
- lineup template
- standings template

Editors/designers create reusable layouts once.

The system dynamically injects:
- scores
- team names
- logos
- player names
- headlines

---

# 3. Fast Content Pipeline

Speed matters.

Target:
- breaking story graphics generated within seconds
- match result graphics generated immediately after full-time

---

# 4. Scalable Media Workflow

The architecture should simulate a modern sports media newsroom:
- data ingestion
- AI assistance
- editorial review
- automated publishing
- analytics tracking

---

# TECH STACK

## Backend
- Python 3.10+
- FastAPI
- Celery
- Redis
- MongoDB
- APScheduler

## AI
- OpenAI APIs

## Media Rendering
- HTML templates
- Tailwind CSS
- Playwright screenshots
- Pillow (optional)

## APIs
- Instagram Graph API
- API-Football

## Deployment
- Docker
- Docker Compose
- AWS-ready architecture

---

# CORE FEATURES

# 1. Football Data Service

Create a modular football data ingestion service.

## Responsibilities
- Fetch live scores
- Fetch fixtures
- Fetch standings
- Fetch match events
- Fetch transfer news
- Fetch breaking football news

## Requirements
- Async HTTP requests
- Retry handling
- Rate limiting
- Response normalization
- Provider abstraction layer

## Suggested Structure

app/
    services/
        football/
            api_client.py
            fixtures.py
            standings.py
            matches.py
            transfers.py
            news.py

---

# 2. AI Content Generation Service

Create an AI-assisted content generation engine.

## Generate
- Instagram captions
- Story text
- Headlines
- Hashtags
- Match summaries
- Breaking news summaries

## Tone
- modern football media style
- exciting
- fast-paced
- Indian audience optimized
- emoji-friendly
- concise

## Example Output

"FULL TIME 🔥

Liverpool dominate Arsenal 3-1 at Anfield ⚽

Salah delivers another masterclass 👑

#Liverpool #PremierLeague"

## Requirements
- reusable prompt templates
- configurable tone profiles
- multilingual support ready
- token optimization

## Structure

app/
    services/
        ai/
            openai_client.py
            prompts/
            caption_generator.py

---

# 3. Graphic Generation Engine

This is the MOST IMPORTANT MODULE.

Build an automated football graphic rendering system.

## Generate
- Match result cards
- Transfer posters
- Breaking news graphics
- Story graphics
- Standings graphics
- Fixture reminders

## Requirements
- reusable templates
- dynamic content injection
- team logos
- player images
- configurable branding
- responsive layouts

## Preferred Approach
Use:
- HTML templates
- Tailwind CSS
- Playwright screenshots

Reason:
- maintainable
- scalable
- designer-friendly

## Output Sizes

### Feed Posts
1080x1080

### Stories
1080x1920

## Folder Structure

app/
    media/
        templates/
            posts/
            stories/
        assets/
            logos/
            fonts/
        renderers/

---

# 4. Instagram Publishing Service

Build a Meta Graph API integration layer.

## Features
- Publish feed posts
- Publish stories
- Schedule publishing
- Retry failed publishing
- Caption publishing
- Media upload handling

## Requirements
- OAuth handling
- Token refresh support
- Centralized API wrapper
- Robust error handling
- Publishing logs

## Structure

app/
    integrations/
        instagram/
            auth.py
            api_client.py
            publisher.py
            stories.py

---

# 5. Story Automation Engine

Stories can be partially automated.

## Story Types
- Match kickoff reminders
- Goal alerts
- Full-time results
- League standings
- Breaking transfer updates

## Rules

### Allowed Auto-Publish
- score updates
- kickoff reminders
- standings

### Requires Approval
- controversial news
- rumors
- sensitive content

---

# 6. Trend Detection System

Build a lightweight football trend engine.

## Sources
- RSS feeds
- football APIs
- Reddit football discussions

## Features
- breaking topic detection
- duplicate filtering
- virality scoring
- priority scoring

## Example Logic

IF:
- same topic appears in multiple sources
- within short timeframe

THEN:
- generate draft breaking-news post

---

# 7. Approval Workflow

IMPORTANT:
No fully autonomous publishing initially.

## Workflow

Automation generates content
    ->
Editor reviews
    ->
Approve / reject
    ->
Publish

## Features
- preview generated images
- edit captions
- edit hashtags
- reschedule posts
- reject low-quality outputs

## APIs

GET /posts/pending
POST /posts/{id}/approve
POST /posts/{id}/reject

---

# 8. Scheduler System

Use:
- APScheduler
- Celery

## Scheduled Jobs

### Every 1 minute
- fetch live scores

### Every 5 minutes
- detect breaking news

### Every 15 minutes
- generate story candidates

### Match end
- trigger result graphic generation

---

# 9. Database Design

MongoDB collections:

- fixtures
- matches
- trends
- generated_posts
- generated_stories
- publishing_logs
- approvals
- ai_generations

## Requirements
- timestamps
- indexes
- retry metadata
- publishing status tracking

---

# 10. API Design

Use FastAPI routers.

## Suggested Routers

/api/posts
/api/stories
/api/news
/api/trends
/api/admin
/api/instagram

---

# 11. Branding System

Create reusable branding configurations.

## Configurable
- fonts
- colors
- gradients
- watermark
- logo placement
- theme layouts

## Example Structure

configs/
    branding/
        default.json
        epl_theme.json

---

# 12. Analytics & Monitoring

Track:
- publishing success
- failed posts
- engagement metrics
- posting times
- content performance

## Requirements
- structured logging
- publishing audit logs
- Celery monitoring
- retry visibility

---

# 13. Security Requirements

- .env configuration
- no hardcoded secrets
- request validation
- API throttling
- token encryption support

---

# 14. Architecture Requirements

Use:
- service layer pattern
- repository pattern
- dependency injection
- async-first design
- clean architecture principles

Keep:
- publishing logic separate
- AI logic modular
- media generation reusable

---

# 15. Folder Structure

app/
    api/
    core/
    services/
        football/
        ai/
        publishing/
    integrations/
        instagram/
    media/
        templates/
        renderers/
        assets/
    workers/
    repositories/
    models/
    schemas/
    utils/

---

# 16. Docker Setup

Create:
- Dockerfile
- docker-compose.yml

## Services
- backend
- redis
- mongodb
- celery_worker
- celery_beat

---

# 17. Future-Proofing

Design architecture for future:
- reels generation
- YouTube Shorts
- Telegram publishing
- WhatsApp Channels
- multilingual publishing
- multi-account support

Do NOT tightly couple publishing to Instagram.

---

# IMPORTANT IMPLEMENTATION NOTES

- keep business logic outside routes
- use reusable retry decorators
- centralize configuration management
- use Pydantic models
- use async database access
- keep templates reusable
- design Celery tasks independently

---

# OUTPUT EXPECTATION

Generate:
1. Full backend architecture
2. FastAPI application setup
3. MongoDB integration
4. Celery integration
5. Football API integration
6. OpenAI integration
7. Instagram Graph API integration
8. Graphic rendering engine
9. Story automation workflows
10. Approval dashboard APIs
11. Scheduler jobs
12. Docker setup
13. Environment configuration
14. Example workflows
15. Production-ready coding patterns
16. Modular scalable architecture