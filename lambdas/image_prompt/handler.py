"""
Image Prompt Generation Lambda  —  Step Functions Task

Generates a structured DALL-E 3 image prompt from the selected content.
Keeps the image generation step separate so the prompt can be reviewed
before spending DALL-E credits.

Input:  { ...previous state..., "caption": "...", "post_type": "..." }
Output: { ...input..., "image_prompt": "DALL-E 3 prompt string" }
"""
from lambdas.shared.openai_client import chat_complete

_PROMPT_SYSTEM = """\
You are a visual art director for a premium football Instagram account.
Your job is to write a detailed DALL-E 3 image generation prompt.

Rules:
- Photorealistic, dramatic football photography style
- No text or logos in the image
- Vivid colours, dynamic motion blur where appropriate
- Output ONLY the image prompt (no explanation, no quotes)
- Max 200 words
"""

_PROMPT_USER_BREAKING = """\
Create a DALL-E 3 image prompt for a breaking football news post.
News topic: {topic}
"""

_PROMPT_USER_TRANSFER = """\
Create a DALL-E 3 image prompt for a football transfer announcement post.
Topic: {topic}
Style: Silhouette of a player signing a contract, club colours in the background.
"""

_PROMPT_USER_MATCH = """\
Create a DALL-E 3 image prompt for a football match result or story post.
Topic: {topic}
Style: Dramatic stadium atmosphere, players celebrating or in action.
"""


def handler(event: dict, context) -> dict:
    post_type = event.get("post_type", "match_result")
    content = event.get("content", {})
    topic = content.get("topic", "football news")

    print(f"[INFO] Generating image prompt | type={post_type} | topic={topic[:60]}")

    if post_type == "breaking_news":
        user = _PROMPT_USER_BREAKING.format(topic=topic)
    elif post_type == "transfer":
        user = _PROMPT_USER_TRANSFER.format(topic=topic)
    else:
        user = _PROMPT_USER_MATCH.format(topic=topic)

    image_prompt = chat_complete(
        _PROMPT_SYSTEM,
        user,
        max_tokens=300,
        temperature=0.7,
    )

    print(f"[INFO] Image prompt: {image_prompt[:100]}...")

    return {**event, "image_prompt": image_prompt}
