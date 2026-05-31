"""
Approval Notifier Lambda  —  Step Functions WaitForTaskToken

Sends an SNS notification (e.g. email) containing an approval/rejection URL
that embeds the Step Functions task token. The reviewer clicks Approve or Reject
which triggers the send_task_success / send_task_failure callback.

Input:
  {
    "task_token": "...",   (injected by Step Functions via $$.Task.Token)
    "post_id": "uuid",
    "caption": "...",
    "image_presigned_url": "...",
    "post_type": "..."
  }

Output: none — this Lambda does not return to Step Functions directly.
The callback URL handler (api-gw endpoint) calls sfn.send_task_success/failure.
"""
import json
import os

import boto3

SNS_TOPIC_ARN = os.environ.get("APPROVAL_SNS_TOPIC_ARN", "")
APPROVAL_API_BASE = os.environ.get("APPROVAL_API_BASE_URL", "")

_sns_client = None


def _get_sns():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _sns_client


def handler(event: dict, context) -> dict:
    task_token = event.get("task_token", "")
    post_id = event.get("post_id", "")
    caption = event.get("caption", "")[:200]
    image_url = event.get("image_presigned_url", "")
    post_type = event.get("post_type", "")

    if not SNS_TOPIC_ARN:
        print("[WARN] APPROVAL_SNS_TOPIC_ARN not set — auto-approving")
        # In dev, just pass through without waiting
        return event

    approve_url = f"{APPROVAL_API_BASE}/approve?token={task_token}&post_id={post_id}"
    reject_url = f"{APPROVAL_API_BASE}/reject?token={task_token}&post_id={post_id}"

    message = f"""
⚽ Football App — Post Approval Required

Post ID: {post_id}
Type:    {post_type}
Caption: {caption}
Preview: {image_url}

APPROVE: {approve_url}
REJECT:  {reject_url}

This token expires in 24 hours.
"""

    _get_sns().publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"[Football App] Approve Post: {post_type}",
        Message=message,
    )

    print(f"[INFO] Approval notification sent | post_id={post_id}")
    return {"notified": True, "post_id": post_id}
