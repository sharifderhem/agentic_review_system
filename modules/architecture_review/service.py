import asyncio
import logging
from time import monotonic
from typing import Any

from config import RepositoryConfig, settings
from integrations.azure_devops.client import AzureDevOpsClient
from integrations.azure_devops.schemas import AzureEvent, Iteration, PullRequest
from integrations.litellm.client import LiteLLMClient
from modules.architecture_review.context import (
    ReviewContext,
    ReviewContextBuilder,
    ReviewFailed,
)
from modules.architecture_review.repository import ArchitectureReviewRepository
from modules.architecture_review.reviewer import ArchitectureReviewer
from modules.architecture_review.schemas import ReviewOutcome, ReviewResult
from modules.event_ingestion.repository import EventRepository
from modules.event_ingestion.service import EventIngestionService
from modules.publication.repository import PublicationRepository
from modules.publication.schemas import PublicationRequest
from modules.publication.service import PublicationService

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, azure: AzureDevOpsClient, litellm: LiteLLMClient):
        self._azure = azure
        self._events = EventIngestionService()
        self._context = ReviewContextBuilder()
        self._reviewer = ArchitectureReviewer(litellm)
        self._publication = PublicationService()

    async def enqueue(self, event: AzureEvent) -> tuple[str, str | None]:
        if settings.get_repository(event.resource.repository.id) is None:
            settings.set_repositories(await self._azure.discover_repositories())
        return await self._events.enqueue(event)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                processed = await self.process_next()
            except Exception:
                logger.exception("worker_iteration_failed")
                processed = False
            if not processed:
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=settings.worker_poll_seconds
                    )
                except TimeoutError:
                    pass

    async def process_next(self) -> bool:
        job = await EventRepository.claim_next()
        if job is None:
            return False
        try:
            await self._process_job(job)
            return True
        except Exception as exc:
            safe_error = str(exc) if isinstance(exc, ReviewFailed) else type(exc).__name__
            logger.warning(
                "review_job_failed job_id=%s attempt=%s error=%s",
                job["id"],
                job["attempts"],
                safe_error,
            )
            if job["attempts"] < settings.worker_max_attempts:
                delay = settings.worker_retry_base_seconds * (
                    2 ** (job["attempts"] - 1)
                )
                await EventRepository.retry(
                    job["id"], job["attempts"], delay, safe_error
                )
            else:
                await self._publish_terminal_failure(job)
                await EventRepository.fail(job["id"], safe_error)
            return True

    async def _process_job(self, job: dict[str, Any]) -> None:
        repository = self._repository(job["repository_id"])
        azure = self._azure.for_repository(repository)
        pr = await azure.get_pull_request(job["pull_request_id"])
        if pr.status != "active" or (
            pr.isDraft and not repository.review_draft_prs
        ):
            await EventRepository.complete(job["id"], "ignored")
            return
        self._validate_pr(pr, repository)
        iterations = await azure.get_iterations(pr.pullRequestId)
        if not iterations:
            raise ReviewFailed("The pull request has no reviewable iterations")
        iteration = iterations[-1]
        if iteration.sourceRefCommit.commitId != job["review_commit"]:
            await EventRepository.complete(job["id"], "superseded", iteration.id)
            return
        publication = await PublicationRepository.get(
            repository.repository_id, pr.pullRequestId, iteration.id
        )
        if publication:
            await EventRepository.complete(
                job["id"], publication["outcome"], iteration.id
            )
            return

        started = monotonic()
        await self._publication.mark_pending(
            azure, repository, pr.pullRequestId, iteration.id
        )
        context = await self._context.build(azure, repository, pr, iteration)
        analysis = await self._reviewer.review(
            context, model=repository.litellm_model
        )
        await self._publication.publish(
            azure,
            repository,
            self._publication_request(pr, iteration, context, analysis.result),
        )
        await ArchitectureReviewRepository.record(
            job_id=job["id"],
            repository=repository,
            pull_request_id=pr.pullRequestId,
            iteration=iteration,
            context=context,
            analysis=analysis,
            duration_ms=int((monotonic() - started) * 1000),
        )
        await EventRepository.complete(
            job["id"], analysis.result.outcome.value, iteration.id
        )

    @staticmethod
    def _repository(repository_id: str) -> RepositoryConfig:
        repository = settings.get_repository(repository_id)
        if repository is None:
            raise ReviewFailed("The repository is not enabled for architecture review")
        return repository

    @staticmethod
    def _validate_pr(
        pr: PullRequest, repository: RepositoryConfig
    ) -> None:
        if pr.repository.id.casefold() != repository.repository_id.casefold():
            raise ReviewFailed("The pull request belongs to another repository")
        if pr.status != "active":
            raise ReviewFailed("The pull request is no longer active")
        if pr.isDraft and not repository.review_draft_prs:
            raise ReviewFailed("Draft pull requests are excluded by configuration")
        if not pr.supportsIterations:
            raise ReviewFailed("The pull request does not support iterations")

    async def _publish_terminal_failure(self, job: dict[str, Any]) -> None:
        try:
            repository = self._repository(job["repository_id"])
            azure = self._azure.for_repository(repository)
            pr = await azure.get_pull_request(job["pull_request_id"])
            if pr.status != "active":
                return
            iterations = await azure.get_iterations(pr.pullRequestId)
            if not iterations:
                return
            iteration = iterations[-1]
            if iteration.sourceRefCommit.commitId != job["review_commit"]:
                return
            result = ReviewResult(
                outcome=ReviewOutcome.REVIEW_FAILED,
                summary=(
                    "The architecture review could not be completed reliably. "
                    "This is not a successful review result."
                ),
            )
            await self._publication.publish(
                azure,
                repository,
                self._publication_request(pr, iteration, None, result),
            )
        except Exception:
            logger.exception("failure_publication_failed job_id=%s", job["id"])

    def _publication_request(
        self,
        pr: PullRequest,
        iteration: Iteration,
        context: ReviewContext | None,
        result: ReviewResult,
    ) -> PublicationRequest:
        return PublicationRequest(
            repository_id=pr.repository.id,
            pull_request_id=pr.pullRequestId,
            iteration_id=iteration.id,
            marker=self._marker(iteration.id),
            content=self._render_comment(result, iteration, context),
            outcome=result.outcome.value,
            status_description=result.outcome.value.replace("_", " "),
        )

    @staticmethod
    def _marker(iteration_id: int) -> str:
        return f"<!-- rts-architecture-review iteration={iteration_id} -->"

    @staticmethod
    def _render_comment(
        result: ReviewResult,
        iteration: Iteration,
        context: ReviewContext | None,
    ) -> str:
        titles = {
            ReviewOutcome.NO_VIOLATIONS: "No architecture violations detected",
            ReviewOutcome.CHANGES_RECOMMENDED: "Changes recommended",
            ReviewOutcome.REVIEW_FAILED: "Review could not be completed",
        }
        lines = [
            ReviewService._marker(iteration.id),
            "## Architecture review",
            "",
            f"**{titles[result.outcome]}**",
            "",
            result.summary,
            "",
            f"Reviewed PR iteration `{iteration.id}` at source commit "
            f"`{iteration.sourceRefCommit.commitId}`.",
        ]
        if context is not None:
            lines.extend(
                [
                    f"PR: {context.pull_request_title}",
                    f"Standards: `{context.standards_path}` from target commit "
                    f"`{iteration.targetRefCommit.commitId}`.",
                ]
            )
            if context.context_documents:
                lines.append(
                    "Required context: "
                    + ", ".join(f"`{path}`" for path in context.context_documents)
                )
        for finding in result.findings:
            location = finding.file + (f":{finding.line}" if finding.line else "")
            lines.extend(
                [
                    "",
                    f"### `{finding.standard}` — `{location}`",
                    finding.explanation,
                    "",
                    f"**Evidence:** {finding.evidence}",
                ]
            )
            if finding.suggestion:
                lines.extend(["", f"**Suggested change:** {finding.suggestion}"])
        if context is not None and context.exclusions:
            lines.extend(["", "**Not reviewed:**"])
            lines.extend(f"- {exclusion}" for exclusion in context.exclusions)
        if result.outcome == ReviewOutcome.NO_VIOLATIONS:
            lines.extend(
                [
                    "",
                    "This result covers only the supplied standards and reviewed "
                    "context. It is not an approval or a guarantee of correctness.",
                ]
            )
        return "\n".join(lines)
