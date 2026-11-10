from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from config import settings


class Database:
    _path = settings.database_path

    @classmethod
    async def initialize(cls) -> None:
        Path(cls._path).parent.mkdir(parents=True, exist_ok=True)
        async with cls.connection() as connection:
            await connection.execute("PRAGMA journal_mode = WAL")
            await connection.execute("PRAGMA synchronous = NORMAL")

    @classmethod
    @asynccontextmanager
    async def connection(cls) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(cls._path) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA busy_timeout = 5000")
            yield connection

    @classmethod
    @asynccontextmanager
    async def transaction(cls) -> AsyncIterator[aiosqlite.Connection]:
        async with cls.connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise

    @classmethod
    async def execute(cls, query: str, params: tuple[Any, ...] = ()) -> int:
        async with cls.connection() as connection:
            cursor = await connection.execute(query, params)
            await connection.commit()
            return cursor.rowcount

    @classmethod
    async def fetch_one(
        cls, query: str, params: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        async with cls.connection() as connection:
            cursor = await connection.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    @classmethod
    async def fetch_all(
        cls, query: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        async with cls.connection() as connection:
            cursor = await connection.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @classmethod
    async def close(cls) -> None:
        return None
