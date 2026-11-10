import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from integrations.azure_devops.router import router
from integrations.azure_devops.schemas import AzureEvent
from tests.fakes import make_event


class FakeService:
    def __init__(self):
        self.events = []

    async def enqueue(self, event: AzureEvent):
        self.events.append(event)
        return "queued", "job-1"


def client(monkeypatch, password="secret"):
    monkeypatch.setattr(settings, "webhook_username", "reviewer")
    monkeypatch.setattr(settings.webhook_password, "get_secret_value", lambda: password)
    app = FastAPI()
    app.include_router(router)
    app.state.review_service = FakeService()
    return TestClient(app)


def auth(username="reviewer", password="secret"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_webhook_requires_authentication(monkeypatch):
    with client(monkeypatch) as test_client:
        response = test_client.post("/webhooks/azure-devops", json=make_event())
    assert response.status_code == 401


def test_webhook_accepts_documented_payload(monkeypatch):
    with client(monkeypatch) as test_client:
        response = test_client.post(
            "/webhooks/azure-devops", json=make_event(), headers=auth()
        )
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "job_id": "job-1"}
    assert test_client.app.state.review_service.events[0].resource.pullRequestId == 22


def test_webhook_rejects_wrong_credentials(monkeypatch):
    with client(monkeypatch) as test_client:
        response = test_client.post(
            "/webhooks/azure-devops", json=make_event(), headers=auth(password="bad")
        )
    assert response.status_code == 401


def test_webhook_rejects_oversized_body(monkeypatch):
    monkeypatch.setattr(settings, "max_webhook_bytes", 100)
    with client(monkeypatch) as test_client:
        response = test_client.post(
            "/webhooks/azure-devops", json=make_event(), headers=auth()
        )
    assert response.status_code == 413
