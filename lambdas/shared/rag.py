"""
DynamoDB-based RAG (Retrieval-Augmented Generation).

Replaces ChromaDB with a lightweight DynamoDB implementation suitable for
AWS Free Tier. Embeddings are stored as lists of floats in DynamoDB and
cosine similarity is computed in Lambda — practical for the ~1,000 articles
retained in the rolling TTL window.

Flow:
  1. Embed query via OpenAI text-embedding-3-small
  2. Scan recent articles from DynamoDB (last 48 h, capped at TOP_K_SCAN_LIMIT)
  3. Compute cosine similarity in Python
  4. Return top-k matches
"""
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from lambdas.shared.dynamodb_client import news_table
from lambdas.shared.openai_client import get_embedding

# Scan at most this many recent articles to keep Lambda latency low
TOP_K_SCAN_LIMIT = int(os.environ.get("RAG_SCAN_LIMIT", "200"))
DEFAULT_TOP_K = int(os.environ.get("RAG_TOP_K", "5"))


# ─── Cosine similarity ────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _decimal_to_float(val) -> float:
    """DynamoDB returns Decimals; convert to float for math."""
    if isinstance(val, Decimal):
        return float(val)
    return val


# ─── Ingest ───────────────────────────────────────────────────────────────────

def store_article_with_embedding(article: dict, embedding: list[float]) -> None:
    """
    Upsert an article + its embedding into DynamoDB.
    Uses article_id as PK and ingested_at as SK.
    Sets a TTL of 72 hours so old articles expire automatically.
    """
    table = news_table()
    now = datetime.now(timezone.utc)
    ttl = int((now + timedelta(hours=72)).timestamp())

    # DynamoDB does not support native float lists; store as Decimal
    embedding_decimal = [Decimal(str(round(v, 8))) for v in embedding]

    table.put_item(
        Item={
            "article_id": article["id"],
            "ingested_at": now.isoformat(),
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "source_name": article.get("source_name", ""),
            "link": article.get("link", ""),
            "published": article.get("published", ""),
            "embedding": embedding_decimal,
            "is_breaking": _flag_breaking(article),
            "is_transfer": _flag_transfer(article),
            "is_world_cup": _flag_world_cup(article),
            "content_score": _score_article(article),
            "expires_at": ttl,
        }
    )


def _flag_breaking(article: dict) -> bool:
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    return any(kw in text for kw in ["breaking", "official", "confirmed", "just in"])


def _flag_transfer(article: dict) -> bool:
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    return any(kw in text for kw in ["transfer", "signs", "joins", "loan", "deal"])


def _flag_world_cup(article: dict) -> bool:
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    return "world cup" in text


def _score_article(article: dict) -> int:
    """
    Priority score used by content selection.
    Higher = more likely to be posted.
    """
    score = 0
    if _flag_breaking(article):
        score += 30
    if _flag_world_cup(article):
        score += 20
    if _flag_transfer(article):
        score += 10
    return score


# ─── Retrieve ─────────────────────────────────────────────────────────────────

def retrieve(query: str, top_k: Optional[int] = None) -> list[dict]:
    """
    Embed query, scan recent DynamoDB articles, compute cosine similarity,
    return top_k ranked hits.
    """
    k = top_k or DEFAULT_TOP_K
    query_embedding = get_embedding(query)

    # Scan articles ingested in the last 48 h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    table = news_table()

    response = table.scan(
        FilterExpression="ingested_at >= :cutoff",
        ExpressionAttributeValues={":cutoff": cutoff},
        ProjectionExpression="article_id, title, source_name, link, published, summary, embedding",
        Limit=TOP_K_SCAN_LIMIT,
    )
    items = response.get("Items", [])

    # Compute cosine similarity for each item
    scored = []
    for item in items:
        raw_emb = item.get("embedding", [])
        if not raw_emb:
            continue
        article_emb = [_decimal_to_float(v) for v in raw_emb]
        sim = _cosine_similarity(query_embedding, article_emb)
        scored.append({
            "title": item.get("title", ""),
            "source_name": item.get("source_name", ""),
            "link": item.get("link", ""),
            "published": item.get("published", ""),
            "summary": item.get("summary", ""),
            "relevance_score": round(sim, 4),
        })

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:k]


def build_context_block(query: str, top_k: Optional[int] = None) -> str:
    """Format retrieved articles as an LLM context block."""
    hits = retrieve(query, top_k=top_k)
    if not hits:
        return ""

    lines = [
        "LATEST FOOTBALL NEWS CONTEXT (sourced today — use this for accurate facts):",
        "---",
    ]
    for i, hit in enumerate(hits, 1):
        snippet = (hit.get("summary") or "")[:300]
        lines.append(
            f"[{i}] {hit['title']} | {hit['source_name']} | {hit['published']}\n"
            f"    {snippet}"
        )
    lines.append("---")
    return "\n".join(lines)
