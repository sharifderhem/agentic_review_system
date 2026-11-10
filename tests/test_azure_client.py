import base64

import httpx
import pytest

from config import RepositoryConfig, settings
from integrations.azure_devops.client import AzureDevOpsClient


def make_client(http: httpx.AsyncClient) -> AzureDevOpsClient:
    return AzureDevOpsClient(
        http,
        repository=RepositoryConfig(
            repository_id="repo-1",
            name="repo-one",
            project="project one",
            base_url=settings.azure_devops_base_url,
            api_version=settings.azure_devops_api_version,
            architecture_standards_path="/AGENTS.md",
            review_draft_prs=False,
            statuses_enabled=True,
            litellm_model=settings.litellm_model,
        ),
    )


@pytest.mark.asyncio
async def test_self_hosted_urls_pat_and_change_pagination(monkeypatch):
    monkeypatch.setattr(
        settings, "azure_devops_base_url", "https://ado.internal/tfs/DefaultCollection"
    )
    monkeypatch.setattr(settings, "azure_page_size", 1)
    monkeypatch.setattr(settings, "azure_devops_api_version", "7.0")
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        skip = int(request.url.params.get("$skip", "0"))
        if skip == 0:
            body = {
                "changeEntries": [
                    {"changeType": "edit", "item": {"path": "/a.py"}}
                ],
                "nextSkip": 1,
            }
        else:
            body = {
                "changeEntries": [
                    {"changeType": "add", "item": {"path": "/b.py"}}
                ],
                "nextSkip": 0,
            }
        return httpx.Response(200, json=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = make_client(http)
    changes = await client.get_changes(22, 3)

    assert len(changes) == 2
    assert str(requests[0].url).startswith(
        "https://ado.internal/tfs/DefaultCollection/project%20one/"
        "_apis/git/repositories/repo-1/pullRequests/22/iterations/3/changes"
    )
    assert requests[0].url.params["api-version"] == "7.0"
    assert requests[1].url.params["$skip"] == "1"
    expected = base64.b64encode(
        f":{settings.azure_devops_pat.get_secret_value()}".encode()
    ).decode()
    assert requests[0].headers["Authorization"] == f"Basic {expected}"
    await http.aclose()


@pytest.mark.asyncio
async def test_file_content_uses_exact_commit():
    seen = None

    def handler(request: httpx.Request):
        nonlocal seen
        seen = request
        return httpx.Response(200, content=b"ARCH-01: Keep handlers thin.")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = make_client(http)
    content = await client.get_file_bytes("/AGENTS.md", "target-commit")

    assert content == b"ARCH-01: Keep handlers thin."
    assert seen.url.params["path"] == "/AGENTS.md"
    assert seen.url.params["versionDescriptor.version"] == "target-commit"
    assert seen.url.params["versionDescriptor.versionType"] == "commit"
    await http.aclose()


@pytest.mark.asyncio
async def test_thread_and_status_request_bodies():
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.method, request.url.path, request.content))
        if request.method == "GET":
            return httpx.Response(200, json={"value": [], "count": 0})
        if request.url.path.endswith("/threads"):
            return httpx.Response(200, json={"id": 91})
        return httpx.Response(200, json={"id": 5})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = make_client(http)
    assert await client.find_thread(22, "missing-marker") is None
    assert await client.create_thread(22, "review text") == 91
    await client.create_status(22, 3, "succeeded", "No violations")

    assert calls[1][0] == "POST"
    assert b'"content":"review text"' in calls[1][2]
    assert b'"iterationId":3' in calls[2][2]
    assert b'"state":"succeeded"' in calls[2][2]
    await http.aclose()
