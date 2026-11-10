import logging

from config import RepositoryConfig
from integrations.azure_devops.client import AzureDevOpsClient
from modules.publication.repository import PublicationRepository
from modules.publication.schemas import PublicationRequest

logger = logging.getLogger(__name__)


class PublicationService:
    async def mark_pending(
        self,
        azure: AzureDevOpsClient,
        repository: RepositoryConfig,
        pull_request_id: int,
        iteration_id: int,
    ) -> None:
        if repository.statuses_enabled:
            await self._safe_status(
                azure,
                pull_request_id,
                iteration_id,
                "pending",
                "Architecture review in progress",
            )

    async def publish(
        self,
        azure: AzureDevOpsClient,
        repository: RepositoryConfig,
        request: PublicationRequest,
    ) -> None:
        thread_id = await azure.find_thread(request.pull_request_id, request.marker)
        if thread_id is None:
            thread_id = await azure.create_thread(
                request.pull_request_id, request.content
            )
        await PublicationRepository.record(
            request.repository_id,
            request.pull_request_id,
            request.iteration_id,
            thread_id,
            request.outcome,
        )
        if repository.statuses_enabled:
            state = "error" if request.outcome == "review_failed" else "succeeded"
            await self._safe_status(
                azure,
                request.pull_request_id,
                request.iteration_id,
                state,
                request.status_description,
            )

    async def _safe_status(
        self,
        azure: AzureDevOpsClient,
        pull_request_id: int,
        iteration_id: int,
        state: str,
        description: str,
    ) -> None:
        try:
            await azure.create_status(
                pull_request_id, iteration_id, state, description
            )
        except Exception:
            logger.warning(
                "status_publication_failed pull_request_id=%s iteration_id=%s",
                pull_request_id,
                iteration_id,
            )
