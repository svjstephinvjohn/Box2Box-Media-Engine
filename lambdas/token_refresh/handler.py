"""
Instagram Token Refresh Lambda

Triggered by: EventBridge schedule (every 45 days)

Instagram long-lived access tokens expire after 60 days.
This Lambda refreshes the token and updates Secrets Manager
before the expiry window closes.
"""
import os
import json

import boto3
import httpx

from lambdas.shared.secrets import get_meta_credentials, get_secret

# Must match the API version used for publishing
META_GRAPH_BASE = "https://graph.facebook.com/v25.0"
META_SECRET_NAME = os.environ.get("META_SECRET_NAME", "football-app/meta")

_sm_client = None


def _get_sm():
    global _sm_client
    if _sm_client is None:
        _sm_client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _sm_client


def handler(event: dict, context) -> dict:
    print("[INFO] Refreshing Instagram long-lived access token")

    creds = get_meta_credentials()
    current_token = creds.get("access_token", "")
    app_id = creds.get("app_id", "")
    app_secret = creds.get("app_secret", "")

    if not all([current_token, app_id, app_secret]):
        raise ValueError("Missing Meta credentials in Secrets Manager")

    # GET with URL-encoded query params — matches:
    #   curl -G "https://graph.facebook.com/v25.0/oauth/access_token" \
    #        --data-urlencode "grant_type=fb_exchange_token" \
    #        --data-urlencode "client_id=..." \
    #        --data-urlencode "client_secret=..." \
    #        --data-urlencode "fb_exchange_token=..."
    # Note: client_id is your Meta App ID, not the Instagram account ID.
    resp = httpx.get(
        f"{META_GRAPH_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": current_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "access_token" not in body:
        raise RuntimeError(f"Token refresh failed: {body}")
    new_token = body["access_token"]

    # Update Secrets Manager with the new token
    updated_secret = {**creds, "access_token": new_token}
    _get_sm().put_secret_value(
        SecretId=META_SECRET_NAME,
        SecretString=json.dumps(updated_secret),
    )

    print("[INFO] Instagram access token refreshed successfully")
    return {"refreshed": True}
