from typing import Literal

from pydantic import BaseModel


class WebhookResponse(BaseModel):
    status: Literal["queued", "duplicate", "ignored"]
    job_id: str | None = None
