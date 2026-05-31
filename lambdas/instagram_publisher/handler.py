"""
Instagram Publisher Lambda  —  Step Functions Task

Publishes the generated post to Instagram via the Meta Graph API.
Updates DynamoDB publishing log with result.

Input:
  {
    "post_id": "uuid",
    "caption": "...",
    "image_presigned_url": "https://...",
    "post_type": "..."
  }

Output:
  { ...input..., "instagram_media_id": "...", "published": true }
"""
import os
from datetime import datetime, timezone

import httpx

from lambdas.shared.secrets import get_meta_credentials
from lambdas.shared.dynamodb_client import posts_table, publishing_log_table

# API version must match what was tested in Graph API Explorer
META_GRAPH_BASE = "https://graph.facebook.com/v25.0"


def _get_account_id() -> str:
    return get_meta_credentials().get("account_id", os.environ.get("INSTAGRAM_ACCOUNT_ID", ""))


def _get_access_token() -> str:
    return get_meta_credentials().get("access_token", "")


def _create_image_container(image_url: str, caption: str, account_id: str, token: str) -> str:
    """
    Step 1: Create a media container.
    Equivalent to:
      curl -X POST "https://graph.facebook.com/v25.0/{account_id}/media" \
           -d "image_url=..." -d "caption=..." -d "access_token=..."
    """
    resp = httpx.post(
        f"{META_GRAPH_BASE}/{account_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "id" not in body:
        raise RuntimeError(f"Media container creation failed: {body}")
    return body["id"]


def _publish_container(container_id: str, account_id: str, token: str) -> str:
    """
    Step 2: Publish the media container.
    Equivalent to:
      curl -X POST "https://graph.facebook.com/v25.0/{account_id}/media_publish" \
           -d "creation_id=..." -d "access_token=..."
    """
    resp = httpx.post(
        f"{META_GRAPH_BASE}/{account_id}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "id" not in body:
        raise RuntimeError(f"Media publish failed: {body}")
    return body["id"]


def _update_post_status(post_id: str, media_id: str) -> None:
    posts_table().update_item(
        Key={"post_id": post_id},
        UpdateExpression="SET #s = :status, instagram_media_id = :mid, published_at = :ts",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "published",
            ":mid": media_id,
            ":ts": datetime.now(timezone.utc).isoformat(),
        },
    )


def _write_publishing_log(post_id: str, media_id: str | None, success: bool, error: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    publishing_log_table().put_item(Item={
        "post_id": post_id,
        "published_at": now,
        "instagram_media_id": media_id or "",
        "status": "success" if success else "failed",
        "error_message": error,
    })


def handler(event: dict, context) -> dict:
    post_id = event.get("post_id", "")
    caption = event.get("caption", "")
    image_url = event.get("image_presigned_url", "")

    if not image_url:
        raise ValueError("image_presigned_url is required")
    if not post_id:
        raise ValueError("post_id is required")

    token = _get_access_token()
    account_id = _get_account_id()

    print(f"[INFO] Publishing to Instagram | post_id={post_id} | account={account_id}")

    try:
        container_id = _create_image_container(image_url, caption, account_id, token)
        media_id = _publish_container(container_id, account_id, token)

        _update_post_status(post_id, media_id)
        _write_publishing_log(post_id, media_id, success=True)

        print(f"[INFO] Published successfully | media_id={media_id}")
        return {**event, "instagram_media_id": media_id, "published": True}

    except Exception as exc:
        error_msg = str(exc)
        print(f"[ERROR] Instagram publish failed: {error_msg}")
        _write_publishing_log(post_id, None, success=False, error=error_msg)
        raise  # Let Step Functions handle retry/catch
