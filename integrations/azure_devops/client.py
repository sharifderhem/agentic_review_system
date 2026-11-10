import base64
from typing import Any
from urllib.parse import quote

import httpx

from config import RepositoryConfig, settings
from integrations.azure_devops.schemas import Iteration, PullRequest


class AzureDevOpsError(RuntimeError):
    pass


class AzureDevOpsClient:
    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        repository: RepositoryConfig | None = None,
        _close_http: bool = True,
    ):
        verify: bool | str = settings.azure_devops_verify_tls
        if settings.azure_devops_ca_bundle:
            verify = settings.azure_devops_ca_bundle
        self._http = http or httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            verify=verify,
        )
        token = settings.azure_devops_pat.get_secret_value()
        basic = base64.b64encode(f":{token}".encode()).decode()
        self._headers = {"Authorization": f"Basic {basic}"}
        self._repository = repository
        self._close_http = _close_http

    def for_repository(
        self, repository: RepositoryConfig
    ) -> "AzureDevOpsClient":
        return AzureDevOpsClient(
            http=self._http,
            repository=repository,
            _close_http=False,
        )

    async def close(self) -> None:
        if self._close_http:
            await self._http.aclose()

    def _resolved_repository(self) -> RepositoryConfig:
        if self._repository is None:
            raise AzureDevOpsError("The Azure DevOps client is not bound to a repository")
        return self._repository

    def _url(self, path: str) -> str:
        repository = self._resolved_repository()
        project = quote(repository.project, safe="")
        repository_id = quote(repository.repository_id, safe="")
        return (
            f"{repository.base_url.rstrip('/')}/{project}"
            f"/_apis/git/repositories/{repository_id}/{path.lstrip('/')}"
        )

    async def _request_url(
        self,
        method: str,
        url: str,
        *,
        api_version: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        accept: str = "application/json",
        allow_404: bool = False,
    ) -> httpx.Response | None:
        query = dict(params or {})
        query["api-version"] = api_version
        headers = {**self._headers, "Accept": accept}
        try:
            response = await self._http.request(
                method,
                url,
                params=query,
                json=json,
                headers=headers,
            )
            if allow_404 and response.status_code == 404:
                return None
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            suffix = f" HTTP {status}" if status is not None else ""
            raise AzureDevOpsError(f"Azure DevOps request failed:{suffix}") from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        accept: str = "application/json",
        allow_404: bool = False,
    ) -> httpx.Response | None:
        return await self._request_url(
            method,
            self._url(path),
            api_version=self._resolved_repository().api_version,
            params=params,
            json=json,
            accept=accept,
            allow_404=allow_404,
        )

    async def discover_repositories(self) -> list[RepositoryConfig]:
        projects: list[dict[str, Any]] = []
        skip = 0
        page_size = 100
        while True:
            response = await self._request_url(
                "GET",
                f"{settings.azure_devops_base_url.rstrip('/')}/_apis/projects",
                api_version=settings.azure_devops_api_version,
                params={"$top": page_size, "$skip": skip},
            )
            page = response.json().get("value", [])
            projects.extend(page)
            if len(page) < page_size:
                break
            skip += len(page)

        repositories: dict[str, RepositoryConfig] = {}
        for project in projects:
            project_name = project.get("name")
            if not project_name:
                raise AzureDevOpsError("Azure DevOps returned a project without a name")
            response = await self._request_url(
                "GET",
                (
                    f"{settings.azure_devops_base_url.rstrip('/')}/"
                    f"{quote(project_name, safe='')}/_apis/git/repositories"
                ),
                api_version=settings.azure_devops_api_version,
            )
            for repository in response.json().get("value", []):
                repository_id = repository.get("id")
                name = repository.get("name")
                if not repository_id or not name:
                    raise AzureDevOpsError(
                        "Azure DevOps returned an incomplete repository record"
                    )
                repositories[repository_id.casefold()] = RepositoryConfig(
                    repository_id=repository_id,
                    name=name,
                    project=project_name,
                    base_url=settings.azure_devops_base_url,
                    api_version=settings.azure_devops_api_version,
                    litellm_model=settings.litellm_model,
                )
        return sorted(
            repositories.values(),
            key=lambda repository: (
                repository.project.casefold(),
                repository.name.casefold(),
            ),
        )

    async def get_pull_request(self, pull_request_id: int) -> PullRequest:
        response = await self._request("GET", f"pullRequests/{pull_request_id}")
        return PullRequest.model_validate(response.json())

    async def get_iterations(self, pull_request_id: int) -> list[Iteration]:
        response = await self._request(
            "GET", f"pullRequests/{pull_request_id}/iterations"
        )
        iterations = [
            Iteration.model_validate(item)
            for item in response.json().get("value", [])
        ]
        return sorted(iterations, key=lambda item: item.id)

    async def get_changes(
        self, pull_request_id: int, iteration_id: int
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        skip = 0
        while True:
            response = await self._request(
                "GET",
                f"pullRequests/{pull_request_id}/iterations/{iteration_id}/changes",
                params={"$top": settings.azure_page_size, "$skip": skip},
            )
            body = response.json()
            page = body.get("changeEntries", [])
            changes.extend(page)
            next_skip = int(body.get("nextSkip", 0) or 0)
            if next_skip == 0:
                return changes
            if next_skip <= skip:
                raise AzureDevOpsError("Azure DevOps pagination did not advance")
            skip = next_skip

    async def get_file_bytes(self, path: str, commit: str) -> bytes | None:
        response = await self._request(
            "GET",
            "items",
            params={
                "path": path,
                "versionDescriptor.version": commit,
                "versionDescriptor.versionType": "commit",
            },
            accept="text/plain",
            allow_404=True,
        )
        return None if response is None else response.content

    async def find_thread(
        self, pull_request_id: int, marker: str
    ) -> int | None:
        response = await self._request("GET", f"pullRequests/{pull_request_id}/threads")
        for thread in response.json().get("value", []):
            if thread.get("isDeleted"):
                continue
            for comment in thread.get("comments", []):
                if comment.get("isDeleted") or marker not in comment.get("content", ""):
                    continue
                if settings.azure_devops_bot_id:
                    author_id = comment.get("author", {}).get("id")
                    if author_id != settings.azure_devops_bot_id:
                        continue
                return int(thread["id"])
        return None

    async def create_thread(self, pull_request_id: int, content: str) -> int:
        response = await self._request(
            "POST",
            f"pullRequests/{pull_request_id}/threads",
            json={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": content,
                        "commentType": "text",
                    }
                ],
                "status": "active",
                "properties": {
                    "Microsoft.TeamFoundation.Discussion.SupportsMarkdown": {
                        "$type": "System.Int32",
                        "$value": 1,
                    }
                },
            },
        )
        return int(response.json()["id"])

    async def create_status(
        self,
        pull_request_id: int,
        iteration_id: int,
        state: str,
        description: str,
    ) -> None:
        await self._request(
            "POST",
            f"pullRequests/{pull_request_id}/statuses",
            json={
                "iterationId": iteration_id,
                "state": state,
                "description": description,
                "context": {
                    "name": "architecture-review",
                    "genre": "rts",
                },
            },
        )
