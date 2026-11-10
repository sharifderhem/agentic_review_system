from pydantic import BaseModel, Field


class CompletionUsage(BaseModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class JSONCompletion(BaseModel):
    content: dict
    model: str | None = None
    usage: CompletionUsage = CompletionUsage()
