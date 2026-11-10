import base64
import hmac
import json
import logging
import xml.etree.ElementTree as ET

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import ValidationError

from config import settings
from integrations.azure_devops.schemas import AzureEvent
from modules.event_ingestion.schemas import WebhookResponse

router = APIRouter(prefix="/webhooks", tags=["reviews"])
logger = logging.getLogger(__name__)

SOAP_RESPONSE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <NotifyResponse xmlns="http://schemas.microsoft.com/TeamFoundation/2005/06/Services/Notification/03" />
  </soap:Body>
</soap:Envelope>"""


def authenticate(request: Request) -> None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode()
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication",
        ) from None
    expected_password = settings.webhook_password.get_secret_value()
    valid = hmac.compare_digest(username, settings.webhook_username)
    valid &= hmac.compare_digest(password, expected_password)
    if not expected_password or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication",
        )


def _xml_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _xml_text(root: ET.Element, name: str) -> str:
    for element in root.iter():
        if _xml_name(element) == name and element.text:
            value = element.text.strip()
            if value:
                return value
    raise ValueError(f"SOAP notification is missing {name}")


def _soap_event(body: bytes) -> AzureEvent:
    upper_body = body.upper()
    if b"<!DOCTYPE" in upper_body or b"<!ENTITY" in upper_body:
        raise ValueError("SOAP document types are not supported")
    envelope = ET.fromstring(body)
    event_xml = _xml_text(envelope, "eventXml").encode("utf-16")
    notification = ET.fromstring(event_xml)
    trigger = _xml_text(notification, "EventTrigger")
    event_type = {
        "PullRequestCreatedNotification": "git.pullrequest.created",
        "PushNotification": "git.pullrequest.updated",
    }.get(trigger, trigger)
    commits = [
        element.get("CommitId")
        for element in notification.iter()
        if _xml_name(element) == "GitPullRequestCommitSummary"
        and element.get("CommitId")
    ]
    return AzureEvent(
        id=_xml_text(notification, "GitNotificationGuid"),
        eventType=event_type,
        resource={
            "repository": {
                "id": _xml_text(notification, "RepositoryId"),
                "name": _xml_text(notification, "RepositoryName"),
            },
            "pullRequestId": int(_xml_text(notification, "PullRequestId")),
            "status": "active",
            "isDraft": _xml_text(notification, "IsDraft").lower() == "true",
            "lastMergeSourceCommit": (
                {"commitId": commits[0]} if commits else None
            ),
        },
    )


@router.post("/azure-devops", response_model=WebhookResponse)
async def receive_azure_devops(request: Request) -> WebhookResponse:
    authenticate(request)
    content_length = request.headers.get("Content-Length")
    if content_length and int(content_length) > settings.max_webhook_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE)
    body = await request.body()
    if len(body) > settings.max_webhook_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE)
    try:
        event = AzureEvent.model_validate(json.loads(body))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY) from None
    outcome, job_id = await request.app.state.review_service.enqueue(event)
    return WebhookResponse(status=outcome, job_id=job_id)


@router.post("/azure-devops/soap")
async def receive_azure_devops_soap(request: Request) -> Response:
    content_length = request.headers.get("Content-Length")
    if content_length and int(content_length) > settings.max_webhook_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE)
    body = await request.body()
    if len(body) > settings.max_webhook_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE)
    try:
        event = _soap_event(body)
    except (ET.ParseError, ValueError, ValidationError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY) from None
    outcome, job_id = await request.app.state.review_service.enqueue(event)
    logger.info(
        "soap_notification_processed event_id=%s pr=%s outcome=%s job_id=%s",
        event.id,
        event.resource.pullRequestId,
        outcome,
        job_id,
    )
    return Response(content=SOAP_RESPONSE, media_type="text/xml")
