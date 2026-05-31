"""
OpenAI client for Lambda functions.

Reads the API key from Secrets Manager on first call, then caches it.
Provides both chat completion and embedding helpers.
"""
import os
from openai import OpenAI
from lambdas.shared.secrets import get_openai_api_key

# Synchronous client — Lambda handlers are synchronous
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_openai_api_key())
    return _client


def chat_complete(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.8,
) -> str:
    """Run a chat completion and return the assistant message text."""
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


def get_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector using text-embedding-3-small.
    Dimension: 1536  |  Cost: $0.02 / 1M tokens  (very cheap)
    """
    model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    client = _get_client()
    response = client.embeddings.create(
        model=model,
        input=text[:8000],  # guard against oversized inputs
    )
    return response.data[0].embedding


def generate_image(prompt: str, size: str = "1024x1024") -> bytes:
    """
    Generate an image with DALL-E 3 and return the raw bytes.
    Replaces the Playwright HTML renderer from the original app.
    """
    client = _get_client()
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        n=1,
        size=size,
        response_format="b64_json",
    )
    import base64
    b64 = response.data[0].b64_json
    return base64.b64decode(b64)
