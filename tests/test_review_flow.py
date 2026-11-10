import pytest

from database import Database
from integrations.azure_devops.schemas import AzureEvent
from modules.architecture_review.service import ReviewService
from tests.fakes import FakeAzure, FakeLiteLLM, make_event


@pytest.mark.asyncio
async def test_complete_mocked_review_and_source_commit_dedup(database):
    azure = FakeAzure()
    model = FakeLiteLLM()
    service = ReviewService(azure, model)

    first = await service.enqueue(AzureEvent.model_validate(make_event()))
    duplicate = await service.enqueue(
        AzureEvent.model_validate(make_event(event_id="event-2"))
    )

    assert first[0] == "queued"
    assert duplicate == ("duplicate", None)
    assert await service.process_next() is True
    assert len(model.calls) == 1
    assert "return 1" in model.calls[0]["unified_diff"]
    assert "return 2" in model.calls[0]["unified_diff"]
    assert len(azure.threads) == 1
    assert "No architecture violations detected" in azure.threads[0]["content"]
    assert [status[1] for status in azure.statuses] == ["pending", "succeeded"]


@pytest.mark.asyncio
async def test_out_of_order_jobs_publish_only_once_for_same_iteration(database):
    azure = FakeAzure()
    service = ReviewService(azure, FakeLiteLLM())
    await service.enqueue(AzureEvent.model_validate(make_event(commit="old")))
    await service.enqueue(
        AzureEvent.model_validate(make_event(event_id="event-2", commit="source-1"))
    )

    await service.process_next()
    await service.process_next()

    assert len(azure.threads) == 1
    completed = await Database.fetch_all(
        "SELECT status FROM review_jobs ORDER BY created_at"
    )
    assert [row["status"] for row in completed] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_model_failure_is_never_reported_as_success(database):
    from integrations.litellm.client import LiteLLMError

    azure = FakeAzure()
    service = ReviewService(
        azure, FakeLiteLLM(error=LiteLLMError("invalid model output"))
    )
    await service.enqueue(AzureEvent.model_validate(make_event()))

    await service.process_next()

    assert "Review could not be completed" in azure.threads[0]["content"]
    job = await Database.fetch_one("SELECT * FROM review_jobs")
    assert job["status"] == "failed"
    assert job["outcome"] == "review_failed"


@pytest.mark.asyncio
async def test_oversized_file_skips_model_and_publishes_failure(database, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_file_bytes", 10)
    azure = FakeAzure()
    model = FakeLiteLLM()
    service = ReviewService(azure, model)
    await service.enqueue(AzureEvent.model_validate(make_event()))

    await service.process_next()

    assert model.calls == []
    assert "Review could not be completed" in azure.threads[0]["content"]


@pytest.mark.asyncio
async def test_closed_pr_is_ignored_without_model_or_comment(database):
    azure = FakeAzure()
    azure.pr.status = "completed"
    model = FakeLiteLLM()
    service = ReviewService(azure, model)
    event = make_event(status="completed")
    assert await service.enqueue(AzureEvent.model_validate(event)) == ("ignored", None)


@pytest.mark.asyncio
async def test_binary_and_generated_files_are_explicit_exclusions(database):
    azure = FakeAzure()
    azure.changes = [
        {
            "changeType": "add",
            "item": {"path": "/assets/logo.png", "isFolder": False},
        },
        {
            "changeType": "add",
            "item": {"path": "/dist/app.js", "isFolder": False},
        },
    ]
    azure.files[("source-1", "/assets/logo.png")] = b"\x89PNG\0binary"
    model = FakeLiteLLM()
    service = ReviewService(azure, model)
    await service.enqueue(AzureEvent.model_validate(make_event()))

    await service.process_next()

    assert len(model.calls[0]["exclusions"]) == 2
    assert len(azure.threads) == 1
