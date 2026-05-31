from openai import AsyncOpenAI
from app.core.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIClient:
    def __init__(self):
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    async def chat_complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 512) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.8,
        )
        content = response.choices[0].message.content or ""
        logger.debug("openai_response", tokens_used=response.usage.total_tokens if response.usage else 0)
        return content.strip()
