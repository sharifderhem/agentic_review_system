# Architecture Review Service

Standalone FastAPI service that receives Azure DevOps PR webhooks, reviews exact PR changes against protected architecture standards through LiteLLM, and publishes an advisory PR comment. It cannot modify source, vote, approve, merge, or block a PR.

## Flow

```text
Azure PAT -> discover accessible projects/repositories
Azure PR webhook -> persistent SQLite job -> latest PR iteration/diff
-> protected /AGENTS.md and its directly linked Markdown documents
-> LiteLLM structured review -> grounding validation -> Azure PR thread/status
```

The model is text-only and receives no Azure credentials or tools. The service stores job, review-run, and publication metadata, not source code, prompts, findings, PATs, or model keys.

## Local setup

```bash
cd architecture-review-service
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/uvicorn main:app --reload --port 8080
```

Real reviews require Azure, LiteLLM, and webhook values in `.env`; never commit that file. At startup, the service lists projects and repositories visible to the Azure identity. An event for an unknown repository triggers one discovery refresh. No repository ID, project name, repository JSON, or context-path list is configured in `.env`.

Health checks:

```bash
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
```

Run only the existing verification suite when needed:

```bash
.venv/bin/python -m pytest -q
```

The test sources have been aligned with the modular refactor, but the suite has not been run after this change.

## Repository discovery and activation

Repository discovery and review activation are separate:

- Discovery lists repositories available to the configured Azure identity.
- A review runs only when Azure sends an eligible PR webhook for a discovered repository.
- Configuring a Service Hook therefore controls which repositories activate reviews. Discovery alone does not publish comments everywhere.
- Project-level Service Hooks can cover their repositories; otherwise configure the intended test repository.

The Azure identity needs permission to list projects/repositories and read PR/content data. During the POC, keep its access limited to the intended test/pilot repositories.

## Repository standards and context

Every reviewed repository uses `/AGENTS.md` from the protected target commit as its architecture standards. No standards path is configured in `.env`.

Direct inline links to repository-local Markdown files in `AGENTS.md` are also read as required context. External links, anchors, images, non-Markdown links, and links inside those additional documents are not followed. Discovery is non-recursive and does not crawl source files.

Document-count, individual-size, and combined-size limits apply. Missing, non-UTF-8, or oversized required documents produce `review_failed`.

Set `AZURE_DEVOPS_BOT_ID` to require matching bot authorship when reconciling existing comment markers.

## Docker

```bash
docker build -t architecture-review-service .
docker run --rm -p 8080:8080 --env-file .env \
  -v architecture-review-data:/app/data architecture-review-service
```

## Configuration and migration

All environment-specific values are documented in `.env.example`. Cloud and self-hosted Azure differ through base URL, PAT, API version, TLS, webhook, and network configuration. The current implementation uses one shared Azure PAT and LiteLLM virtual key; keep their scopes restricted.

Migrations are numbered SQL files in `migrations/`, executed by the Python migration runner. Never edit an applied migration; add the next number. The runner also supports a future `baseline_N.sql` for fresh installations after squashing history. Existing databases then continue with numbered migrations newer than their recorded `PRAGMA user_version`.

## Documentation

- [Project and implementation map](AGENTS.md) — service boundaries, LiteLLM/AI Hub integration, repository layout, and working rules. Start here when developing the service.
- [RTS AI-enabled engineering strategy](RTS_AI_Engineering_Strategy.md) — product goals, milestone scope, and future phases.
- [Research process and candidate results](research_results.md) — build-versus-adopt research and open decisions.
- [Azure DevOps integration contract](docs/azure-devops-integration.md) — API behavior, reliability, and security constraints.
- [Access request and smoke test](docs/devops-access-request.md) — company onboarding and real integration verification.

This `README.md` covers the service overview and local commands; `AGENTS.md` covers the implementation and contributor context. The local suite uses documented payloads and mocked Azure/LiteLLM HTTP calls. Real company Azure DevOps behavior is intentionally not claimed as verified until the smoke test runs.
