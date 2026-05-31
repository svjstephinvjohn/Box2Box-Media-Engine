"""
Smoke tests for Lambda handlers using moto (AWS mocks).

Run with: pytest tests/test_main.py -v
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock

# Set env vars before any imports that touch AWS/OpenAI
os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "NEWS_ARTICLES_TABLE": "football-news-articles",
    "GENERATED_POSTS_TABLE": "football-generated-posts",
    "PUBLISHING_LOG_TABLE": "football-publishing-log",
    "TRENDS_TABLE": "football-trends",
    "IMAGES_BUCKET_NAME": "test-images-bucket",
    "OPENAI_SECRET_NAME": "football-app/openai",
    "META_SECRET_NAME": "football-app/meta",
    "API_FOOTBALL_SECRET_NAME": "football-app/api-football",
    "DAILY_POST_LIMIT": "5",
    "APPROVAL_MODE": "auto",
    "CONTENT_PIPELINE_SFN_ARN": "arn:aws:states:us-east-1:000000000000:stateMachine:test",
})


# ── Content Selection ─────────────────────────────────────────────────────────

class TestContentSelection:
    """Test content_selection Lambda handler."""

    def test_no_content_when_table_empty(self):
        """Returns content_found=False when no recent trends exist."""
        try:
            from moto import mock_aws
        except ImportError:
            pytest.skip("moto not installed")

        import boto3
        with mock_aws():
            # Create DynamoDB tables
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            ddb.create_table(
                TableName="football-trends",
                KeySchema=[
                    {"AttributeName": "trend_id", "KeyType": "HASH"},
                    {"AttributeName": "detected_at", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "trend_id", "AttributeType": "S"},
                    {"AttributeName": "detected_at", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            ddb.create_table(
                TableName="football-generated-posts",
                KeySchema=[
                    {"AttributeName": "post_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "post_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            # Invalidate cached DynamoDB table refs
            import lambdas.shared.dynamodb_client as dc
            dc.get_table.cache_clear()
            dc._dynamodb = None

            from lambdas.content_selection.handler import handler
            result = handler({}, None)

        assert result["content_found"] is False

    def test_daily_limit_stops_selection(self):
        """Returns content_found=False when daily post limit is reached."""
        try:
            from moto import mock_aws
        except ImportError:
            pytest.skip("moto not installed")

        import boto3
        from datetime import datetime, timezone
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            posts_table = ddb.create_table(
                TableName="football-generated-posts",
                KeySchema=[
                    {"AttributeName": "post_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "post_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            ddb.create_table(
                TableName="football-trends",
                KeySchema=[
                    {"AttributeName": "trend_id", "KeyType": "HASH"},
                    {"AttributeName": "detected_at", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "trend_id", "AttributeType": "S"},
                    {"AttributeName": "detected_at", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            # Insert 5 posts created today
            now = datetime.now(timezone.utc).isoformat()
            for i in range(5):
                posts_table.put_item(Item={"post_id": f"p{i}", "created_at": now, "status": "published"})

            import lambdas.shared.dynamodb_client as dc
            dc.get_table.cache_clear()
            dc._dynamodb = None

            from lambdas.content_selection import handler as h
            import importlib; importlib.reload(h)
            result = h.handler({}, None)

        assert result["content_found"] is False
        assert result["reason"] == "daily_limit_reached"


# ── Caption Generation ────────────────────────────────────────────────────────

class TestCaptionGeneration:
    """Test caption_generation Lambda handler with mocked OpenAI and RAG."""

    def test_generates_caption_for_breaking_news(self):
        mock_caption = "BREAKING: Big football news! #Football #BreakingNews"

        with patch("lambdas.shared.rag.retrieve", return_value=[]), \
             patch("lambdas.shared.openai_client.chat_complete", return_value=mock_caption):

            from lambdas.caption_generation.handler import handler
            event = {
                "post_type": "breaking_news",
                "content": {"topic": "Player signs new mega deal"},
                "approval_mode": "auto",
            }
            result = handler(event, None)

        assert result["caption"] == mock_caption
        assert result["post_type"] == "breaking_news"

    def test_generates_caption_for_transfer(self):
        mock_caption = "Welcome to the club! ⚽ #Transfer #Football"

        with patch("lambdas.shared.rag.retrieve", return_value=[]), \
             patch("lambdas.shared.openai_client.chat_complete", return_value=mock_caption):

            from lambdas.caption_generation.handler import handler
            event = {
                "post_type": "transfer",
                "content": {"topic": "Mbappe to Arsenal"},
                "approval_mode": "auto",
            }
            result = handler(event, None)

        assert result["caption"] == mock_caption


# ── Image Prompt Generation ───────────────────────────────────────────────────

class TestImagePromptGeneration:
    def test_returns_image_prompt_field(self):
        mock_prompt = "Dramatic football stadium at night, player celebrating, photorealistic"

        with patch("lambdas.shared.openai_client.chat_complete", return_value=mock_prompt):
            from lambdas.image_prompt.handler import handler
            event = {
                "post_type": "match_result",
                "content": {"topic": "Liverpool 3-1 Arsenal"},
                "caption": "What a match!",
            }
            result = handler(event, None)

        assert result["image_prompt"] == mock_prompt

