from typing import Optional
from app.services.ai.openai_client import OpenAIClient
from app.services.ai.prompts.match_result import MATCH_RESULT_SYSTEM, MATCH_RESULT_USER
from app.services.ai.prompts.transfer import TRANSFER_SYSTEM, TRANSFER_USER
from app.services.ai.prompts.breaking_news import BREAKING_NEWS_SYSTEM, BREAKING_NEWS_USER
from app.services.rag.dynamodb_retriever import DynamoDBNewsRetriever as NewsRetriever
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CaptionGenerator:
    def __init__(self, client: OpenAIClient, retriever: Optional[NewsRetriever] = None):
        self._client = client
        # Retriever is optional; if absent, context block is empty (graceful degradation)
        self._retriever = retriever or NewsRetriever()

    def _get_context(self, query: str) -> str:
        try:
            return self._retriever.build_context_block(query)
        except Exception as e:
            # Never let RAG failure block caption generation
            logger.warning("rag_context_fetch_failed", query=query[:60], error=str(e))
            return ""

    async def generate_match_result_caption(
        self,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        league: str,
        events: str = "",
    ) -> str:
        query = f"{home_team} vs {away_team} {league} match result"
        context_block = self._get_context(query)
        system_prompt = MATCH_RESULT_SYSTEM.format(context_block=context_block)
        user_prompt = MATCH_RESULT_USER.format(
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            league=league,
            events=events or "N/A",
        )
        caption = await self._client.chat_complete(system_prompt, user_prompt)
        logger.info("caption_generated", type="match_result", rag_used=bool(context_block))
        return caption

    async def generate_transfer_caption(
        self,
        player_name: str,
        from_team: str,
        to_team: str,
        fee: str = "Undisclosed",
        transfer_type: str = "Permanent",
    ) -> str:
        query = f"{player_name} transfer {from_team} to {to_team}"
        context_block = self._get_context(query)
        system_prompt = TRANSFER_SYSTEM.format(context_block=context_block)
        user_prompt = TRANSFER_USER.format(
            player_name=player_name,
            from_team=from_team,
            to_team=to_team,
            fee=fee,
            transfer_type=transfer_type,
        )
        caption = await self._client.chat_complete(system_prompt, user_prompt)
        logger.info("caption_generated", type="transfer", rag_used=bool(context_block))
        return caption

    async def generate_breaking_news_caption(self, headline: str, summary: str = "") -> str:
        context_block = self._get_context(headline)
        system_prompt = BREAKING_NEWS_SYSTEM.format(context_block=context_block)
        user_prompt = BREAKING_NEWS_USER.format(headline=headline, summary=summary or "N/A")
        caption = await self._client.chat_complete(system_prompt, user_prompt)
        logger.info("caption_generated", type="breaking_news", rag_used=bool(context_block))
        return caption

