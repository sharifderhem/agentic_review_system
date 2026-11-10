import re
from pathlib import Path

from database import Database

MIGRATIONS_DIR = Path(__file__).parent
MIGRATION_PATTERN = re.compile(r"^(\d+)_.+\.sql$")
BASELINE_PATTERN = re.compile(r"^baseline_(\d+)\.sql$")


async def apply_migrations() -> None:
    current_version = await _current_version()
    if current_version == 0:
        baselines = sorted(
            (
                (int(match.group(1)), path)
                for path in MIGRATIONS_DIR.glob("baseline_*.sql")
                if (match := BASELINE_PATTERN.match(path.name))
            ),
            reverse=True,
        )
        if baselines:
            current_version, baseline_path = baselines[0]
            await _apply_sql(baseline_path)
    migrations = sorted(
        (int(match.group(1)), path)
        for path in MIGRATIONS_DIR.glob("[0-9]*_*.sql")
        if (match := MIGRATION_PATTERN.match(path.name))
    )
    for version, path in migrations:
        if version > current_version:
            await _apply_sql(path)
            current_version = version


async def _current_version() -> int:
    async with Database.connection() as connection:
        cursor = await connection.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        return int(row[0])


async def _apply_sql(path: Path) -> None:
    async with Database.connection() as connection:
        try:
            await connection.executescript(path.read_text(encoding="utf-8"))
        except Exception:
            await connection.rollback()
            raise
