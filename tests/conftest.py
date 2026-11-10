import pytest_asyncio

from config import RepositoryConfig, settings
from database import Database
from migrations.migrations import apply_migrations


@pytest_asyncio.fixture
async def database(tmp_path, monkeypatch):
    Database._path = str(tmp_path / "test.db")
    monkeypatch.setattr(settings, "azure_devops_base_url", "https://dev.azure.com/org")
    monkeypatch.setattr(
        settings,
        "_repositories",
        [
            RepositoryConfig(
                repository_id="repo-1",
                name="repo-one",
                project="project one",
                base_url="https://dev.azure.com/org",
                api_version="7.1",
                litellm_model=settings.litellm_model,
            )
        ],
    )
    monkeypatch.setattr(settings, "statuses_enabled", True)
    monkeypatch.setattr(settings, "review_draft_prs", False)
    monkeypatch.setattr(settings, "worker_max_attempts", 1)
    monkeypatch.setattr(settings, "max_changed_files", 200)
    monkeypatch.setattr(settings, "max_file_bytes", 100_000)
    monkeypatch.setattr(settings, "max_diff_bytes", 400_000)
    await Database.initialize()
    await apply_migrations()
    yield Database
