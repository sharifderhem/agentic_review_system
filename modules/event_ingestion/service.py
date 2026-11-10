from config import settings
from integrations.azure_devops.schemas import AzureEvent
from modules.event_ingestion.repository import EventRepository


class EventIngestionService:
    async def enqueue(self, event: AzureEvent) -> tuple[str, str | None]:
        if event.eventType not in {
            "git.pullrequest.created",
            "git.pullrequest.updated",
        }:
            return "ignored", None
        resource = event.resource
        repository = settings.get_repository(resource.repository.id)
        if repository is None:
            return "ignored", None
        if resource.status != "active":
            return "ignored", None
        if resource.isDraft and not repository.review_draft_prs:
            return "ignored", None
        if resource.lastMergeSourceCommit is None:
            return "ignored", None
        queued, job_id = await EventRepository.enqueue(
            event.id,
            repository.repository_id,
            resource.pullRequestId,
            resource.lastMergeSourceCommit.commitId,
        )
        return ("queued" if queued else "duplicate"), (job_id if queued else None)
