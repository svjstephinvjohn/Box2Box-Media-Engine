"""
DynamoDB-backed RAG retriever — replaces ChromaDB for AWS deployment.

Keeps the same interface as the original NewsRetriever so existing
services (CaptionGenerator etc.) work without changes.
"""
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import boto3

from app.core.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _get_dynamodb():
    settings = get_settings()
    return boto3.resource("dynamodb", region_name=settings.aws_region)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class DynamoDBNewsRetriever:
    """
    Drop-in replacement for ChromaDB-based NewsRetriever.
    Embeds the query via OpenAI, scans recent DynamoDB articles,
    computes cosine similarity in-process, and returns top-k hits.
    """

    def retrieve(self, query: str, top_k: Optional[int] = None) -> list[dict]:
        settings = get_settings()
        k = top_k or settings.rag_top_k

        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=query[:8000],
        )
        query_embedding = resp.data[0].embedding

        # Scan articles from the last 48 hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        table = _get_dynamodb().Table(settings.news_articles_table)

        scan_response = table.scan(
            FilterExpression="ingested_at >= :cutoff",
            ExpressionAttributeValues={":cutoff": cutoff},
            ProjectionExpression=(
                "article_id, title, source_name, #lnk, published, summary, embedding"
            ),
            ExpressionAttributeNames={"#lnk": "link"},
            Limit=settings.rag_scan_limit,
        )

        items = scan_response.get("Items", [])
        scored = []
        for item in items:
            raw_emb = item.get("embedding", [])
            if not raw_emb:
                continue
            article_emb = [float(v) for v in raw_emb]
            sim = _cosine_similarity(query_embedding, article_emb)
            scored.append({
                "title": item.get("title", ""),
                "source_name": item.get("source_name", ""),
                "link": item.get("link", ""),
                "published": item.get("published", ""),
                "document": item.get("summary", ""),
                "relevance_score": round(sim, 4),
            })

        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        hits = scored[:k]
        logger.debug("dynamodb_rag_retrieval", query=query[:60], hits=len(hits))
        return hits

    def build_context_block(self, query: str, top_k: Optional[int] = None) -> str:
        hits = self.retrieve(query, top_k=top_k)
        if not hits:
            return ""

        lines = ["LATEST FOOTBALL NEWS CONTEXT (sourced today — use this for accurate facts):", "---"]
        for i, hit in enumerate(hits, 1):
            snippet = (hit.get("document") or "")[:300]
            lines.append(
                f"[{i}] {hit['title']} | {hit['source_name']} | {hit['published']}\n"
                f"    {snippet}"
            )
        lines.append("---")
        return "\n".join(lines)
