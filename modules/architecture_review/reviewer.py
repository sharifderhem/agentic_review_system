from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from integrations.litellm.client import LiteLLMClient
from integrations.litellm.schemas import JSONCompletion
from modules.architecture_review.context import ReviewContext
from modules.architecture_review.context import ReviewFailed
from modules.architecture_review.schemas import ReviewOutcome, ReviewResult

PROMPT_VERSION = "architecture-review-v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"


@dataclass(frozen=True)
class ReviewAnalysis:
    result: ReviewResult
    completion: JSONCompletion
    prompt_version: str


class ArchitectureReviewer:
    def __init__(self, litellm: LiteLLMClient):
        self._litellm = litellm
        self._system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    async def review(
        self, context: ReviewContext, *, model: str
    ) -> ReviewAnalysis:
        completion = await self._litellm.complete_json(
            system_prompt=self._system_prompt,
            input_data={
                "repository": {
                    "name": context.repository_name,
                    "id": context.repository_id,
                },
                "pull_request_title": context.pull_request_title,
                "architecture_standards": {
                    "path": context.standards_path,
                    "content": context.standards,
                },
                "required_context_documents": [
                    {"path": path, "content": content}
                    for path, content in context.context_documents.items()
                ],
                "coverage": {
                    "changed_files": context.changed_file_count,
                    "reviewed_files": len(context.reviewable_paths),
                    "excluded_files": context.exclusions,
                    "coverage_is_complete": True,
                },
                "unified_diff": context.unified_diff,
            },
            model=model,
        )
        try:
            result = ReviewResult.model_validate(completion.content)
        except ValidationError as exc:
            raise ReviewFailed("The model response violated the review contract") from exc
        self._validate_grounding(result, context)
        return ReviewAnalysis(
            result=result,
            completion=completion,
            prompt_version=PROMPT_VERSION,
        )

    @staticmethod
    def _validate_grounding(result: ReviewResult, context: ReviewContext) -> None:
        if result.outcome != ReviewOutcome.CHANGES_RECOMMENDED:
            return
        standards = context.standards.casefold()
        standards_path = context.standards_path.casefold()
        reviewable_paths = {
            path.lstrip("/"): path for path in context.reviewable_paths
        }
        for finding in result.findings:
            standard = finding.standard.casefold()
            if standard != standards_path and standard not in standards:
                raise ReviewFailed("A finding references an unknown architecture standard")
            normalized_path = finding.file.lstrip("/")
            if normalized_path not in reviewable_paths:
                raise ReviewFailed("A finding references a file outside the reviewed diff")
            finding.file = reviewable_paths[normalized_path]
