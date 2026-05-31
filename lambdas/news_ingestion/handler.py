"""
News Ingestion Lambda

Triggered by: EventBridge schedule (every 30 minutes)

Responsibilities:
1. Fetch articles from RSS football news feeds
2. Generate OpenAI embeddings for each article
3. Store articles + embeddings in DynamoDB (with 72-hour TTL)
4. Detect trending topics and store in DynamoDB
5. Start Step Functions execution for content pipeline
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import boto3
import feedparser

from lambdas.shared.rag import store_article_with_embedding, _flag_breaking, _flag_transfer, _flag_world_cup
from lambdas.shared.openai_client import get_embedding
from lambdas.shared.dynamodb_client import news_table, trends_table

# ─── Configuration ────────────────────────────────────────────────────────────

RSS_SOURCES = [
    {"name": "BBC Sport Football", "url": "https://feeds.bbci.co.uk/sport/football/rss.xml"},
    {"name": "Sky Sports Football", "url": "https://www.skysports.com/rss/12040"},
    {"name": "Goal.com", "url": "https://www.goal.com/feeds/en/news"},
    {"name": "ESPN Soccer", "url": "https://www.espn.com/espn/rss/soccer/news"},
    {"name": "The Guardian Football", "url": "https://www.theguardian.com/football/rss"},
    {"name": "90min", "url": "https://www.90min.com/posts.rss"},
    {"name": "UEFA Champions League", "url": "https://www.uefa.com/rssfeed/uefachampionsleague/"},
]

TREND_KEYWORDS = [
    "transfer", "signing", "injury", "sacked", "fired", "goal", "hat-trick",
    "penalty", "red card", "champions league", "premier league", "world cup",
]

MIN_ARTICLES_FOR_TREND = 2
MAX_PER_SOURCE = int(os.environ.get("MAX_ARTICLES_PER_SOURCE", "15"))
SFN_ARN = os.environ.get("CONTENT_PIPELINE_SFN_ARN", "")

_sfn_client = None


def _get_sfn():
    global _sfn_client
    if _sfn_client is None:
        _sfn_client = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _sfn_client


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _fetch_rss() -> list[dict]:
    articles = []
    for source in RSS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:MAX_PER_SOURCE]:
                url = entry.get("link", "")
                if not url:
                    continue
                articles.append({
                    "id": _article_id(url),
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": url,
                    "published": entry.get("published", ""),
                    "source_name": source["name"],
                    "source_url": source["url"],
                })
        except Exception as exc:
            print(f"[WARN] RSS fetch error {source['name']}: {exc}")
    return articles


def _detect_trends(articles: list[dict]) -> list[dict]:
    topic_map: dict[str, dict] = {}
    for article in articles:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        keywords = [kw for kw in TREND_KEYWORDS if kw in text]
        if not keywords:
            continue
        key = article["title"][:80].lower()
        if key not in topic_map:
            topic_map[key] = {
                "topic": article["title"],
                "keywords": keywords,
                "occurrence_count": 1,
                "is_breaking": _flag_breaking(article),
                "is_transfer": _flag_transfer(article),
                "is_world_cup": _flag_world_cup(article),
            }
        else:
            topic_map[key]["occurrence_count"] += 1

    trends = []
    for key, data in topic_map.items():
        occ = data["occurrence_count"]
        kw_count = len(data["keywords"])
        virality = min(10.0, occ * 1.5 + kw_count * 0.5)

        # Boost priority for high-value content types
        priority = virality
        if data["is_breaking"]:
            priority += 5
        if data["is_world_cup"]:
            priority += 3
        if data["is_transfer"]:
            priority += 2

        trends.append({**data, "virality_score": virality, "priority_score": priority})

    return sorted(trends, key=lambda t: t["priority_score"], reverse=True)


def _store_trend(trend: dict) -> None:
    from decimal import Decimal
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    ttl = int((now + timedelta(hours=24)).timestamp())
    table = trends_table()
    table.put_item(Item={
        "trend_id": str(uuid.uuid4()),
        "detected_at": now.isoformat(),
        "topic": trend["topic"],
        "keywords": trend["keywords"],
        "virality_score": Decimal(str(round(trend["virality_score"], 4))),
        "priority_score": Decimal(str(round(trend["priority_score"], 4))),
        "is_breaking": trend["is_breaking"],
        "is_transfer": trend["is_transfer"],
        "is_world_cup": trend["is_world_cup"],
        "occurrence_count": trend["occurrence_count"],
        "draft_post_generated": False,
        "expires_at": ttl,
    })


# ─── Handler ──────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    print("[INFO] News ingestion started")

    articles = _fetch_rss()
    print(f"[INFO] Fetched {len(articles)} articles from {len(RSS_SOURCES)} sources")

    ingested = 0
    for article in articles:
        try:
            text = f"{article['title']}\n{article.get('summary', '')}"[:1000]
            embedding = get_embedding(text)
            store_article_with_embedding(article, embedding)
            ingested += 1
        except Exception as exc:
            print(f"[WARN] Failed to embed/store article '{article.get('title', '')}': {exc}")

    print(f"[INFO] Ingested {ingested}/{len(articles)} articles with embeddings")

    trends = _detect_trends(articles)
    for trend in trends[:20]:  # store top 20 trends max
        try:
            _store_trend(trend)
        except Exception as exc:
            print(f"[WARN] Failed to store trend: {exc}")

    print(f"[INFO] Stored {min(len(trends), 20)} trends")

    # Start the content pipeline Step Functions execution
    if SFN_ARN:
        try:
            _get_sfn().start_execution(
                stateMachineArn=SFN_ARN,
                name=f"pipeline-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}",
                input=json.dumps({"triggered_by": "news_ingestion", "article_count": ingested}),
            )
            print("[INFO] Content pipeline Step Functions execution started")
        except Exception as exc:
            print(f"[WARN] Failed to start Step Functions: {exc}")
    else:
        print("[WARN] CONTENT_PIPELINE_SFN_ARN not set — skipping Step Functions trigger")

    return {
        "statusCode": 200,
        "articles_fetched": len(articles),
        "articles_ingested": ingested,
        "trends_detected": len(trends),
    }
