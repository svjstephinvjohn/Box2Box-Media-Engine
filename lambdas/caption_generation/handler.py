"""
Caption Generation Lambda  —  Step Functions Task

Input (from Step Functions):
  {
    "content_found": true,
    "post_type": "breaking_news" | "transfer" | "match_result",
    "content": { "topic": "...", "is_breaking": true, ... },
    "approval_mode": "auto",
    "daily_posts_today": 2
  }

Output:
  { ...input..., "caption": "Generated Instagram caption text..." }

Uses DynamoDB-based RAG retrieval + OpenAI GPT-4o.
"""
import os
from lambdas.shared.rag import build_context_block
from lambdas.shared.openai_client import chat_complete

# ─── Prompt templates (inline — avoids extra import paths in Lambda) ──────────

_BREAKING_NEWS_SYSTEM = """\
You are a professional football social media manager creating viral Instagram captions.
Write punchy, emoji-rich captions that drive high engagement.
Keep it under 220 characters. Include 3-5 relevant hashtags at the end.

{context_block}
"""

_BREAKING_NEWS_USER = """\
Write an Instagram caption for this breaking football news:
HEADLINE: {headline}
SUMMARY: {summary}
"""

_TRANSFER_SYSTEM = """\
You are a football transfer expert writing Instagram captions for a top football account.
Be exciting and factual. Use emojis. Keep under 220 characters. Add 3-5 hashtags.

{context_block}
"""

_TRANSFER_USER = """\
Write an Instagram caption for this transfer:
PLAYER: {player}
FROM: {from_team}
TO: {to_team}
"""

_MATCH_RESULT_SYSTEM = """\
You are a football commentator writing Instagram captions for match results.
Be energetic. Mention key moments if known. Under 220 characters. Add 3-5 hashtags.

{context_block}
"""

_MATCH_RESULT_USER = """\
Write an Instagram caption for this football story:
TOPIC: {topic}
"""


# ─── Caption generation helpers ───────────────────────────────────────────────

def _generate_breaking_news_caption(topic: str) -> str:
    context = build_context_block(topic)
    system = _BREAKING_NEWS_SYSTEM.format(context_block=context)
    user = _BREAKING_NEWS_USER.format(headline=topic, summary="")
    return chat_complete(system, user, max_tokens=300)


def _generate_transfer_caption(topic: str) -> str:
    context = build_context_block(topic)
    system = _TRANSFER_SYSTEM.format(context_block=context)
    # Extract player and teams from topic if possible, else use raw topic
    user = _TRANSFER_USER.format(player=topic, from_team="?", to_team="?")
    return chat_complete(system, user, max_tokens=300)


def _generate_match_result_caption(topic: str) -> str:
    context = build_context_block(topic)
    system = _MATCH_RESULT_SYSTEM.format(context_block=context)
    user = _MATCH_RESULT_USER.format(topic=topic)
    return chat_complete(system, user, max_tokens=300)


# ─── Handler ──────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    post_type = event.get("post_type", "match_result")
    content = event.get("content", {})
    topic = content.get("topic", "")

    print(f"[INFO] Generating caption | type={post_type} | topic={topic[:60]}")

    if post_type == "breaking_news":
        caption = _generate_breaking_news_caption(topic)
    elif post_type == "transfer":
        caption = _generate_transfer_caption(topic)
    else:
        caption = _generate_match_result_caption(topic)

    print(f"[INFO] Caption generated ({len(caption)} chars)")

    return {**event, "caption": caption}
