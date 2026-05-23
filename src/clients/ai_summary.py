"""OpenRouter-backed AI summary helper."""

import logging

from aiohttp import ClientError, ClientResponseError

from src.clients.openrouter import OpenRouterClient
from src.config.env_config import Env

logger = logging.getLogger(__name__)


def get_openrouter_client() -> OpenRouterClient | None:
    """Create an OpenRouter client when credentials are configured."""
    if not Env.OPENROUTER_API_KEY:
        return None
    return OpenRouterClient(Env.OPENROUTER_API_KEY, Env.OPENROUTER_MODEL)


async def summarize_signal(context: str) -> str | None:
    """Summarize a strategy signal via OpenRouter; None when AI is unconfigured."""
    client = get_openrouter_client()
    if client is None:
        return None
    prompt = (
        "Summarize this crypto trading signal objectively in Traditional Chinese. "
        "Do not make trading decisions.\n\n"
        f"{context}"
    )
    try:
        return await client.generate_text(prompt)
    except ClientResponseError as exc:
        if exc.status in (402, 429):
            logger.warning("OpenRouter quota exhausted (HTTP %s).", exc.status)
            return "（AI 摘要略過：OpenRouter 額度不足）"
        logger.warning("OpenRouter request failed (HTTP %s).", exc.status)
        return f"（AI 摘要略過：OpenRouter 請求失敗 HTTP {exc.status}）"
    except (ClientError, TimeoutError) as exc:
        logger.warning("OpenRouter request failed: %s", exc)
        return "（AI 摘要略過：OpenRouter 連線失敗）"


async def append_summary(message: str) -> str:
    """Return the message with an AI summary paragraph appended when available."""
    summary = await summarize_signal(message)
    return f"{message}\n\n{summary}" if summary else message
