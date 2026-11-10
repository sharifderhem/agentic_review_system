from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from database import Database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventRepository:
    @staticmethod
    async def enqueue(
        event_id: str,
        repository_id: str,
        pull_request_id: int,
        review_commit: str,
    ) -> tuple[bool, str]:
        job_id = str(uuid4())
        now = utc_now()
        changes = await Database.execute(
            """
            INSERT OR IGNORE INTO review_jobs (
                id, event_id, repository_id, pull_request_id, review_commit,
                status, attempts, available_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?)
            """,
            (
                job_id,
                event_id,
                repository_id,
                pull_request_id,
                review_commit,
                now,
                now,
                now,
            ),
        )
        return changes == 1, job_id

    @staticmethod
    async def claim_next() -> dict[str, Any] | None:
        now = utc_now()
        async with Database.transaction() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM review_jobs
                WHERE status IN ('queued', 'retry') AND available_at <= ?
                ORDER BY created_at LIMIT 1
                """,
                (now,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            await connection.execute(
                """
                UPDATE review_jobs
                SET status = 'processing', attempts = attempts + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            claimed = dict(row)
            claimed["status"] = "processing"
            claimed["attempts"] += 1
            return claimed

    @staticmethod
    async def reset_processing() -> None:
        await Database.execute(
            """
            UPDATE review_jobs SET status = 'queued', updated_at = ?
            WHERE status = 'processing'
            """,
            (utc_now(),),
        )

    @staticmethod
    async def complete(
        job_id: str,
        outcome: str,
        iteration_id: int | None = None,
    ) -> None:
        await Database.execute(
            """
            UPDATE review_jobs
            SET status = 'completed', outcome = ?, iteration_id = ?,
                error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (outcome, iteration_id, utc_now(), job_id),
        )

    @staticmethod
    async def retry(
        job_id: str, attempts: int, delay_seconds: float, error: str
    ) -> None:
        available = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        await Database.execute(
            """
            UPDATE review_jobs
            SET status = 'retry', attempts = ?, available_at = ?,
                error = ?, updated_at = ?
            WHERE id = ?
            """,
            (attempts, available.isoformat(), error[:500], utc_now(), job_id),
        )

    @staticmethod
    async def fail(job_id: str, error: str) -> None:
        await Database.execute(
            """
            UPDATE review_jobs
            SET status = 'failed', outcome = 'review_failed', error = ?, updated_at = ?
            WHERE id = ?
            """,
            (error[:500], utc_now(), job_id),
        )
