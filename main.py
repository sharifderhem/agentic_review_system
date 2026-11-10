import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from config import settings
from database import Database
from integrations.azure_devops.client import AzureDevOpsClient
from integrations.azure_devops.router import router as azure_devops_router
from integrations.litellm.client import LiteLLMClient
from migrations.migrations import apply_migrations
from modules.architecture_review.service import ReviewService
from modules.event_ingestion.repository import EventRepository


class HealthResponse(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    await Database.initialize()
    await apply_migrations()
    await EventRepository.reset_processing()
    azure = AzureDevOpsClient()
    settings.set_repositories(await azure.discover_repositories())
    litellm = LiteLLMClient()
    app.state.review_service = ReviewService(azure, litellm)
    stop = asyncio.Event()
    worker = asyncio.create_task(app.state.review_service.run(stop))
    try:
        yield
    finally:
        stop.set()
        await worker
        await azure.close()
        await litellm.close()


app = FastAPI(title="Architecture Review Service", lifespan=lifespan)
app.include_router(azure_devops_router)


@app.get("/health/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    await Database.fetch_one("SELECT 1 AS ready")
    return HealthResponse(status="ready")
