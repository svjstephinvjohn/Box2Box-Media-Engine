"""
DynamoDB RAG pipeline tests using moto (AWS mock).

Run with: pytest tests/test_rag_pipeline.py -v
"""
import os
import math
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "NEWS_ARTICLES_TABLE": "football-news-articles",
    "RAG_TOP_K": "5",
    "RAG_SCAN_LIMIT": "50",
})


def _make_table(ddb):
    return ddb.create_table(
        TableName="football-news-articles",
        KeySchema=[
            {"AttributeName": "article_id", "KeyType": "HASH"},
            {"AttributeName": "ingested_at", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "article_id", "AttributeType": "S"},
            {"AttributeName": "ingested_at", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


class TestDynamoDBRAG:
    """Tests for lambdas/shared/rag.py — DynamoDB cosine-similarity retrieval."""

    def test_store_and_retrieve(self):
        """Articles stored with embeddings are retrievable via cosine similarity."""
        try:
            from moto import mock_aws
        except ImportError:
            pytest.skip("moto not installed")

        import boto3
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            _make_table(ddb)

            import lambdas.shared.dynamodb_client as dc
            dc.get_table.cache_clear()
            dc._dynamodb = None

            from lambdas.shared.rag import store_article_with_embedding, retrieve

            # Two articles with synthetic embeddings
            liverpool_emb = [1.0, 0.0, 0.0] + [0.0] * 1533
            transfer_emb  = [0.0, 1.0, 0.0] + [0.0] * 1533

            store_article_with_embedding(
                {"id": "a1", "title": "Liverpool beat Arsenal 3-1",
                 "summary": "Salah scored twice", "source_name": "BBC",
                 "link": "http://x.com/1", "published": "2026-05-31"},
                liverpool_emb,
            )
            store_article_with_embedding(
                {"id": "a2", "title": "Mbappe signs new deal",
                 "summary": "French forward extends contract", "source_name": "Guardian",
                 "link": "http://x.com/2", "published": "2026-05-31"},
                transfer_emb,
            )

            # Query embedding most similar to liverpool_emb
            query_emb = [0.9, 0.1, 0.0] + [0.0] * 1533
            with patch("lambdas.shared.rag.get_embedding", return_value=query_emb):
                hits = retrieve("Liverpool match result", top_k=2)

        assert len(hits) == 2
        # Liverpool article should rank first
        assert "Liverpool" in hits[0]["title"]
        assert hits[0]["relevance_score"] > hits[1]["relevance_score"]

    def test_cosine_similarity_math(self):
        """Cosine similarity of identical vectors is 1.0."""
        from lambdas.shared.rag import _cosine_similarity
        vec = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-9

    def test_cosine_similarity_orthogonal(self):
        """Cosine similarity of orthogonal vectors is 0.0."""
        from lambdas.shared.rag import _cosine_similarity
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_context_block_format(self):
        """build_context_block returns non-empty string when hits exist."""
        try:
            from moto import mock_aws
        except ImportError:
            pytest.skip("moto not installed")

        import boto3
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            _make_table(ddb)

            import lambdas.shared.dynamodb_client as dc
            dc.get_table.cache_clear()
            dc._dynamodb = None

            from lambdas.shared.rag import store_article_with_embedding, build_context_block

            emb = [1.0] + [0.0] * 1535
            store_article_with_embedding(
                {"id": "b1", "title": "World Cup Final Tonight",
                 "summary": "Brazil face France", "source_name": "ESPN",
                 "link": "http://x.com/3", "published": "2026-05-31"},
                emb,
            )

            with patch("lambdas.shared.rag.get_embedding", return_value=emb):
                block = build_context_block("World Cup")

        assert "LATEST FOOTBALL NEWS CONTEXT" in block
        assert "World Cup Final" in block

