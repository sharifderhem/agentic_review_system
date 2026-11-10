import pytest

from database import Database
from migrations.migrations import apply_migrations
from modules.event_ingestion.repository import EventRepository


@pytest.mark.asyncio
async def test_migrations_are_repeatable(database):
    await apply_migrations()
    row = await Database.fetch_one("PRAGMA user_version")
    assert row["user_version"] == 2
    tables = await Database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
    names = {table["name"] for table in tables}
    assert {"review_jobs", "review_publications", "architecture_review_runs"}.issubset(names)


@pytest.mark.asyncio
async def test_interrupted_processing_job_returns_to_queue(database):
    queued, job_id = await EventRepository.enqueue("event-1", "repo-1", 22, "commit")
    assert queued
    claimed = await EventRepository.claim_next()
    assert claimed["status"] == "processing"

    await EventRepository.reset_processing()

    job = await Database.fetch_one("SELECT * FROM review_jobs WHERE id = ?", (job_id,))
    assert job["status"] == "queued"
