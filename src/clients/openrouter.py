"""OpenRouter REST client."""

from typing import Any

import aiohttp


class OpenRouterClient:
    """Minimal OpenRouter client using the OpenAI-compatible REST endpoint."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def generate_text(self, prompt: str) -> str | None:
        """Generate a text response for `prompt`."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                response.raise_for_status()
                data = await response.json()

        choices = data.get("choices", [])
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str):
            return None
        return content.strip() or None
