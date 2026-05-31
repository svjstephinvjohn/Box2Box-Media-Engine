from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = "development"
    app_debug: bool = True

    # ── AWS ───────────────────────────────────────────────────────────────────
    aws_region: str = "us-east-1"

    # DynamoDB table names (injected by CDK as Lambda environment variables)
    news_articles_table: str = "football-news-articles"
    generated_posts_table: str = "football-generated-posts"
    publishing_log_table: str = "football-publishing-log"
    trends_table: str = "football-trends"

    # S3 bucket for generated images
    images_bucket_name: str = ""

    # Secrets Manager secret names (Lambdas resolve actual keys from these)
    openai_secret_name: str = "football-app/openai"
    meta_secret_name: str = "football-app/meta"
    api_football_secret_name: str = "football-app/api-football"

    # ── OpenAI (local dev fallback; Lambda reads from Secrets Manager) ────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── RAG ───────────────────────────────────────────────────────────────────
    rag_top_k: int = 5
    rag_scan_limit: int = 200

    # ── Publishing ────────────────────────────────────────────────────────────
    daily_post_limit: int = 5
    approval_mode: str = "auto"  # "auto" | "approval_required"


@lru_cache
def get_settings() -> Settings:
    return Settings()
