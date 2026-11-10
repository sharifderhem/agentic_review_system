import json

import httpx
import pytest

from config import settings
from integrations.litellm.client import LiteLLMClient, LiteLLMError


@pytest.mark.asyncio
async def test_litellm_request_and_structured_response():
    seen = None

    def handler(request: httpx.Request):
        nonlocal seen
        seen = request
        return httpx.Response(
            200,
            json={
                "model": settings.litellm_model,
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "outcome": "no_violations",
                                    "summary": "No violations found.",
                                    "findings": [],
                                }
                            )
                        }
                    }
                ],
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = LiteLLMClient(http)
    result = await client.complete_json(
        system_prompt="Review",
        input_data={"diff": "diff"},
        model=settings.litellm_model,
    )

    assert result.content["outcome"] == "no_violations"
    body = json.loads(seen.content)
    assert body["model"] == settings.litellm_model
    assert body["response_format"] == {"type": "json_object"}
    assert seen.headers["Authorization"].startswith("Bearer ")
    assert seen.url.path == "/v1/chat/completions"
    await http.aclose()


@pytest.mark.asyncio
async def test_invalid_model_json_is_an_error():
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "not json"}}]}
            )
        )
    )
    client = LiteLLMClient(http)
    with pytest.raises(LiteLLMError):
        await client.complete_json(
            system_prompt="Review",
            input_data={"diff": "diff"},
            model=settings.litellm_model,
        )
    await http.aclose()
