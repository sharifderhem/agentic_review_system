from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ReviewOutcome(str, Enum):
    NO_VIOLATIONS = "no_violations"
    CHANGES_RECOMMENDED = "changes_recommended"
    REVIEW_FAILED = "review_failed"


class Finding(BaseModel):
    standard: str = Field(min_length=1, max_length=200)
    file: str = Field(min_length=1, max_length=1000)
    line: int | None = Field(default=None, ge=1)
    explanation: str = Field(min_length=1, max_length=3000)
    evidence: str = Field(min_length=1, max_length=1500)
    suggestion: str = Field(default="", max_length=3000)


class ReviewResult(BaseModel):
    outcome: ReviewOutcome
    summary: str = Field(min_length=1, max_length=6000)
    findings: list[Finding] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_findings(self) -> "ReviewResult":
        if self.outcome == ReviewOutcome.CHANGES_RECOMMENDED and not self.findings:
            raise ValueError("changes_recommended requires at least one finding")
        if self.outcome != ReviewOutcome.CHANGES_RECOMMENDED and self.findings:
            raise ValueError("findings are allowed only for changes_recommended")
        return self
