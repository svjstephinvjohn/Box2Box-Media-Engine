"""
Image Generation Lambda  —  Step Functions Task

Calls DALL-E 3 to generate an image, uploads it to S3, and creates a pending
post record in DynamoDB.

Input:  { ...state..., "image_prompt": "...", "caption": "...", "post_type": "..." }
Output: { ...input..., "post_id": "uuid", "image_s3_key": "posts/uuid.png" }
"""
import io
import os
import uuid
from datetime import datetime, timezone, timedelta

import boto3

from lambdas.shared.openai_client import generate_image
from lambdas.shared.dynamodb_client import posts_table

S3_BUCKET = os.environ.get("IMAGES_BUCKET_NAME", "")
IMAGE_SIZE = os.environ.get("DALLE_IMAGE_SIZE", "1024x1024")

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _s3_client


def _upload_to_s3(image_bytes: bytes, s3_key: str) -> str:
    """Upload image to S3 and return the public URL."""
    _get_s3().put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=image_bytes,
        ContentType="image/png",
        # Images are accessible via presigned URL; bucket stays private
    )
    return f"s3://{S3_BUCKET}/{s3_key}"


def _get_presigned_url(s3_key: str, expires_seconds: int = 3600) -> str:
    return _get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": s3_key},
        ExpiresIn=expires_seconds,
    )


def _create_post_record(post_id: str, event: dict, s3_key: str) -> None:
    now = datetime.now(timezone.utc)
    ttl = int((now + timedelta(days=30)).timestamp())
    posts_table().put_item(Item={
        "post_id": post_id,
        "created_at": now.isoformat(),
        "post_type": event.get("post_type", "match_result"),
        "caption": event.get("caption", ""),
        "image_s3_key": s3_key,
        "source_topic": event.get("content", {}).get("topic", ""),
        "trend_id": event.get("content", {}).get("trend_id", ""),
        "status": "pending",
        "approval_mode": event.get("approval_mode", "auto"),
        "expires_at": ttl,
    })


def handler(event: dict, context) -> dict:
    image_prompt = event.get("image_prompt", "")
    if not image_prompt:
        raise ValueError("image_prompt is required")

    if not S3_BUCKET:
        raise EnvironmentError("IMAGES_BUCKET_NAME environment variable is not set")

    post_id = str(uuid.uuid4())
    s3_key = f"posts/{post_id}.png"

    print(f"[INFO] Generating image | post_id={post_id} | prompt={image_prompt[:80]}...")
    image_bytes = generate_image(image_prompt, size=IMAGE_SIZE)

    print(f"[INFO] Uploading {len(image_bytes)} bytes to s3://{S3_BUCKET}/{s3_key}")
    _upload_to_s3(image_bytes, s3_key)

    # Generate a 1-hour presigned URL for the Instagram publisher
    presigned_url = _get_presigned_url(s3_key, expires_seconds=3600)

    _create_post_record(post_id, event, s3_key)
    print(f"[INFO] Post record created | post_id={post_id}")

    return {
        **event,
        "post_id": post_id,
        "image_s3_key": s3_key,
        "image_presigned_url": presigned_url,
    }
