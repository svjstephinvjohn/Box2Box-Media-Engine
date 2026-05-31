"""
AWS Secrets Manager client for Lambda functions.

Caches secrets in memory for the lifetime of the Lambda execution context
to avoid repeated Secrets Manager API calls (cost + latency).
"""
import json
import os
import boto3
from functools import lru_cache

# Boto3 client is reused across warm invocations
_sm_client = None


def _get_client():
    global _sm_client
    if _sm_client is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _sm_client = boto3.client("secretsmanager", region_name=region)
    return _sm_client


@lru_cache(maxsize=16)
def get_secret(secret_name: str) -> dict:
    """
    Retrieve and parse a JSON secret from Secrets Manager.
    Result is cached for the Lambda container lifetime.
    """
    client = _get_client()
    response = client.get_secret_value(SecretId=secret_name)
    secret_string = response.get("SecretString", "{}")
    return json.loads(secret_string)


def get_openai_api_key() -> str:
    secret_name = os.environ.get("OPENAI_SECRET_NAME", "football-app/openai")
    return get_secret(secret_name)["api_key"]


def get_meta_credentials() -> dict:
    """Returns dict with: app_id, app_secret, access_token, account_id"""
    secret_name = os.environ.get("META_SECRET_NAME", "football-app/meta")
    return get_secret(secret_name)


def get_api_football_key() -> str:
    secret_name = os.environ.get("API_FOOTBALL_SECRET_NAME", "football-app/api-football")
    return get_secret(secret_name)["api_key"]
