import json

from config import RepositoryConfig
from database import Database
from integrations.azure_devops.schemas import Iteration
from modules.architecture_review.context import ReviewContext
from modules.architecture_review.reviewer import ReviewAnalysis
from modules.event_ingestion.repository import utc_now


class ArchitectureReviewRepository:
    @staticmethod
    async def record(
        *,
        job_id: str,
        repository: RepositoryConfig,
        pull_request_id: int,
        iteration: Iteration,
        context: ReviewContext,
        analysis: ReviewAnalysis,
        duration_ms: int,
    ) -> None:
        await Database.execute(
            """
            INSERT OR IGNORE INTO architecture_review_runs (
                job_id, repository_id, pull_request_id, iteration_id,
                source_commit, common_commit, target_commit,
                standards_path, context_documents_json, prompt_version, model,
                changed_file_count, reviewed_file_count, excluded_file_count,
                outcome, duration_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                repository.repository_id,
                pull_request_id,
                iteration.id,
                iteration.sourceRefCommit.commitId,
                iteration.commonRefCommit.commitId,
                iteration.targetRefCommit.commitId,
                context.standards_path,
                json.dumps(list(context.context_documents)),
                analysis.prompt_version,
                analysis.completion.model or repository.litellm_model,
                context.changed_file_count,
                len(context.reviewable_paths),
                len(context.exclusions),
                analysis.result.outcome.value,
                duration_ms,
                utc_now(),
            ),
        )
