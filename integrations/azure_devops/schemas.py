from pydantic import BaseModel, ConfigDict, Field


class AzureRepository(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None


class AzureCommit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    commitId: str


class AzureEventResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repository: AzureRepository
    pullRequestId: int = Field(gt=0)
    status: str = "active"
    isDraft: bool = False
    lastMergeSourceCommit: AzureCommit | None = None


class AzureEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    eventType: str
    resource: AzureEventResource


class PullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pullRequestId: int
    status: str
    isDraft: bool = False
    title: str = ""
    supportsIterations: bool = True
    sourceRefName: str
    targetRefName: str
    repository: AzureRepository


class Iteration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(gt=0)
    sourceRefCommit: AzureCommit
    commonRefCommit: AzureCommit
    targetRefCommit: AzureCommit
