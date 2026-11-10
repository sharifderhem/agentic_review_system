import json
from typing import Any

import httpx
from pydantic import ValidationError

from config import settings
from integrations.litellm.schemas import JSONCompletion


class LiteLLMError(RuntimeError):
    pass


class LiteLLMClient:
    def __init__(self, http: httpx.AsyncClient | None = None):
        self._http = http or httpx.AsyncClient(
            timeout=settings.litellm_timeout_seconds
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def complete_json(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        model: str,
    ) -> JSONCompletion:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(input_data)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": settings.review_temperature,
            "max_tokens": settings.litellm_max_output_tokens,
        }
        try:
            response = await self._http.post(
                f"{settings.litellm_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": (
                        f"Bearer {settings.litellm_api_key.get_secret_value()}"
                    )
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Model content is not text")
            content = content.strip()
            if content.startswith("```"):
                content = content.removeprefix("```json").removeprefix("```")
                content = content.removesuffix("```").strip()
            return JSONCompletion(
                content=json.loads(content),
                model=body.get("model"),
                usage=body.get("usage") or {},
            )
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise LiteLLMError("LiteLLM returned no valid JSON completion") from exc
