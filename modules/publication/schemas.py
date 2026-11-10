from pydantic import BaseModel, Field


class PublicationRequest(BaseModel):
    repository_id: str = Field(min_length=1)
    pull_request_id: int = Field(gt=0)
    iteration_id: int = Field(gt=0)
    marker: str = Field(min_length=1)
    content: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    status_description: str = Field(min_length=1)
