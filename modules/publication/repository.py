from datetime import datetime, timezone
from typing import Any

from database import Database


class PublicationRepository:
    @staticmethod
    async def get(
        repository_id: str, pull_request_id: int, iteration_id: int
    ) -> dict[str, Any] | None:
        return await Database.fetch_one(
            """
            SELECT * FROM review_publications
            WHERE repository_id = ? AND pull_request_id = ? AND iteration_id = ?
            """,
            (repository_id, pull_request_id, iteration_id),
        )

    @staticmethod
    async def record(
        repository_id: str,
        pull_request_id: int,
        iteration_id: int,
        thread_id: int,
        outcome: str,
    ) -> None:
        await Database.execute(
            """
            INSERT OR IGNORE INTO review_publications (
                repository_id, pull_request_id, iteration_id,
                thread_id, outcome, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                repository_id,
                pull_request_id,
                iteration_id,
                thread_id,
                outcome,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
