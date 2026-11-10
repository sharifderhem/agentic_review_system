BEGIN IMMEDIATE;

CREATE TABLE architecture_review_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE REFERENCES review_jobs(id),
    repository_id TEXT NOT NULL,
    pull_request_id INTEGER NOT NULL,
    iteration_id INTEGER NOT NULL,
    source_commit TEXT NOT NULL,
    common_commit TEXT NOT NULL,
    target_commit TEXT NOT NULL,
    standards_path TEXT NOT NULL,
    context_documents_json TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    changed_file_count INTEGER NOT NULL,
    reviewed_file_count INTEGER NOT NULL,
    excluded_file_count INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX architecture_review_runs_pr_idx
ON architecture_review_runs (repository_id, pull_request_id, iteration_id);

PRAGMA user_version = 2;
COMMIT;
