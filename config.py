from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ARCHITECTURE_STANDARDS_PATH = "/AGENTS.md"


class RepositoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    project: str = Field(min_length=1)
    base_url: str
    api_version: str
    architecture_standards_path: str = DEFAULT_ARCHITECTURE_STANDARDS_PATH
    review_draft_prs: bool = False
    statuses_enabled: bool = True
    litellm_model: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    _repositories: list[RepositoryConfig] = PrivateAttr(default_factory=list)

    database_path: str = "./data/app.db"
    log_level: str = "INFO"

    azure_devops_base_url: str = "https://dev.azure.com/example"
    azure_devops_pat: SecretStr = SecretStr("")
    azure_devops_api_version: str = "7.1"
    azure_devops_verify_tls: bool = True
    azure_devops_ca_bundle: str | None = None
    azure_devops_bot_id: str = ""

    webhook_username: str = "architecture-review"
    webhook_password: SecretStr = SecretStr("")
    max_webhook_bytes: int = Field(default=2_000_000, gt=0, le=2_000_000)

    litellm_base_url: str = "http://localhost:4000/v1"
    litellm_api_key: SecretStr = SecretStr("")
    litellm_model: str = "openrouter/gpt-4.1-mini"
    litellm_timeout_seconds: float = Field(default=120, gt=0)
    litellm_max_output_tokens: int = Field(default=4000, gt=0)
    review_temperature: float = Field(default=0, ge=0, le=2)

    review_draft_prs: bool = False
    statuses_enabled: bool = True
    max_changed_files: int = Field(default=200, gt=0)
    max_file_bytes: int = Field(default=100_000, gt=0)
    max_diff_bytes: int = Field(default=400_000, gt=0)
    max_context_documents: int = Field(default=10, gt=0)
    max_context_document_bytes: int = Field(default=100_000, gt=0)
    max_total_context_bytes: int = Field(default=200_000, gt=0)
    azure_page_size: int = Field(default=200, gt=0, le=2000)
    http_timeout_seconds: float = Field(default=30, gt=0)
    worker_poll_seconds: float = Field(default=1, gt=0)
    worker_max_attempts: int = Field(default=5, gt=0)
    worker_retry_base_seconds: float = Field(default=2, gt=0)

    def set_repositories(self, repositories: list[RepositoryConfig]) -> None:
        self._repositories = [
            repository.model_copy(
                update={
                    "architecture_standards_path": DEFAULT_ARCHITECTURE_STANDARDS_PATH,
                    "review_draft_prs": self.review_draft_prs,
                    "statuses_enabled": self.statuses_enabled,
                    "litellm_model": self.litellm_model,
                }
            )
            for repository in repositories
        ]

    def get_repository(self, repository_id: str) -> RepositoryConfig | None:
        return next(
            (
                item
                for item in self._repositories
                if item.repository_id.casefold() == repository_id.casefold()
            ),
            None,
        )


settings = Settings()
