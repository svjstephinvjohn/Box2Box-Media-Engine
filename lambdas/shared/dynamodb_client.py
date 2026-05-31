"""
DynamoDB client helpers for all Lambda functions.

Table names come from environment variables so CDK can inject them
without hard-coding ARNs.
"""
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from functools import lru_cache

# Reuse DynamoDB resource across warm invocations
_dynamodb = None


def _get_resource():
    global _dynamodb
    if _dynamodb is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _dynamodb = boto3.resource("dynamodb", region_name=region)
    return _dynamodb


@lru_cache(maxsize=8)
def get_table(table_name_env: str):
    """
    Return a DynamoDB Table object.
    table_name_env: environment variable key whose value is the table name.
    """
    table_name = os.environ[table_name_env]
    return _get_resource().Table(table_name)


# ─── Convenience accessors ───────────────────────────────────────────────────

def news_table():
    return get_table("NEWS_ARTICLES_TABLE")


def posts_table():
    return get_table("GENERATED_POSTS_TABLE")


def publishing_log_table():
    return get_table("PUBLISHING_LOG_TABLE")


def trends_table():
    return get_table("TRENDS_TABLE")
