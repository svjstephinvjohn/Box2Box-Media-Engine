"""
Content Selection Lambda  —  Step Functions Task

Input (from Step Functions):
  {
    "triggered_by": "news_ingestion",
    "article_count": 12
  }

Output (passed to next Step Functions state):
  {
    "content_found": true,
    "post_type": "breaking_news" | "transfer" | "match_result",
    "content": { ...topic data },
    "approval_mode": "auto" | "approval_required",
    "daily_posts_today": 3
  }

Responsibilities:
1. Read top-priority trends from DynamoDB
2. Deduplicate (skip topics already posted today)
3. Check daily post limit
4. Classify content type
5. Select best candidate
"""
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

from lambdas.shared.dynamodb_client import trends_table, posts_table

DAILY_POST_LIMIT = int(os.environ.get("DAILY_POST_LIMIT", "5"))
APPROVAL_MODE = os.environ.get("APPROVAL_MODE", "auto")  # "auto" | "approval_required"


def _count_posts_today() -> int:
    """Count posts already created today (UTC)."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    table = posts_table()
    response = table.scan(
        FilterExpression="created_at >= :today",
        ExpressionAttributeValues={":today": today_start},
        Select="COUNT",
    )
    return response.get("Count", 0)


def _get_top_trends(limit: int = 10) -> list[dict]:
    """Scan recent trends ordered by priority score."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    table = trends_table()
    response = table.scan(
        FilterExpression="detected_at >= :cutoff AND draft_post_generated = :false",
        ExpressionAttributeValues={":cutoff": cutoff, ":false": False},
    )
    items = response.get("Items", [])

    # Sort by priority_score descending
    items.sort(key=lambda x: float(x.get("priority_score", 0)), reverse=True)
    return items[:limit]


def _already_posted(topic: str) -> bool:
    """Check if a similar topic was already posted in the last 24 h."""
    topic_lower = topic.lower()[:80]
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    table = posts_table()

    response = table.scan(
        FilterExpression="created_at >= :cutoff",
        ExpressionAttributeValues={":cutoff": cutoff},
        ProjectionExpression="source_topic",
    )
    for item in response.get("Items", []):
        stored_topic = (item.get("source_topic") or "").lower()[:80]
        if stored_topic and stored_topic == topic_lower:
            return True
    return False


def _classify_post_type(trend: dict) -> str:
    if trend.get("is_breaking"):
        return "breaking_news"
    if trend.get("is_transfer"):
        return "transfer"
    return "match_result"


def handler(event: dict, context) -> dict:
    print(f"[INFO] Content selection started | input={event}")

    posts_today = _count_posts_today()
    if posts_today >= DAILY_POST_LIMIT:
        print(f"[INFO] Daily post limit reached ({posts_today}/{DAILY_POST_LIMIT})")
        return {"content_found": False, "reason": "daily_limit_reached"}

    trends = _get_top_trends()
    if not trends:
        print("[INFO] No recent trends found")
        return {"content_found": False, "reason": "no_trends"}

    # Pick the first non-duplicate trend
    selected = None
    for trend in trends:
        if not _already_posted(trend.get("topic", "")):
            selected = trend
            break

    if not selected:
        print("[INFO] All recent trends already posted")
        return {"content_found": False, "reason": "all_duplicates"}

    post_type = _classify_post_type(selected)
    print(f"[INFO] Selected trend: '{selected['topic']}' | type={post_type}")

    # Convert Decimal fields for JSON serialisation
    content = {
        "trend_id": selected.get("trend_id"),
        "topic": selected.get("topic"),
        "keywords": selected.get("keywords", []),
        "is_breaking": selected.get("is_breaking", False),
        "is_transfer": selected.get("is_transfer", False),
        "is_world_cup": selected.get("is_world_cup", False),
        "virality_score": float(selected.get("virality_score", 0)),
        "priority_score": float(selected.get("priority_score", 0)),
    }

    return {
        "content_found": True,
        "post_type": post_type,
        "content": content,
        "approval_mode": APPROVAL_MODE,
        "daily_posts_today": posts_today,
    }
