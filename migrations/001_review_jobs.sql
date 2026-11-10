BEGIN IMMEDIATE;

CREATE TABLE review_jobs (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    repository_id TEXT NOT NULL,
    pull_request_id INTEGER NOT NULL,
    review_commit TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    iteration_id INTEGER,
    outcome TEXT,
    error TEXT,
    UNIQUE (repository_id, pull_request_id, review_commit)
);

CREATE INDEX review_jobs_claim_idx
ON review_jobs (status, available_at, created_at);

CREATE TABLE review_publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id TEXT NOT NULL,
    pull_request_id INTEGER NOT NULL,
    iteration_id INTEGER NOT NULL,
    thread_id INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (repository_id, pull_request_id, iteration_id)
);

PRAGMA user_version = 1;
COMMIT;
