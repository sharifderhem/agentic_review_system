# AGENTS.md — Architecture Review Service

## What this is

A standalone FastAPI repository and service for advisory architecture reviews of Azure DevOps pull requests. It receives PR webhooks, persists review jobs, reads current PR changes and protected repository guidance, requests a structured review through LiteLLM, and publishes a PR comment with an optional informational status.

This service is intentionally separate from the AI Hub repository and deployment. It is a **client of AI Hub's LiteLLM gateway**, not another LiteLLM component. It does not deploy or configure LiteLLM, OpenRouter, the AI Hub database, Redis, guardrails, audit synchronization, dashboards, or model providers.

The review is advisory only. The service cannot modify source, vote, approve, merge, or block a PR. It discovers repositories visible to its Azure identity, while Service Hooks control which repositories activate reviews. Rollout should still begin with a controlled test and pilot repository.

## External systems and trust boundaries

```text
Azure DevOps Server/Services
  │  Repository discovery and PR created/source-push webhook
  ▼
Architecture Review Service
  ├── SQLite: durable jobs, retries, deduplication, run/publication metadata
  ├── Azure DevOps REST: repositories, PR iterations, exact files, comments/statuses
  └── HTTPS + dedicated virtual key
          ▼
      AI Hub / LiteLLM
          ▼
      OpenRouter and cloud models
```

### LiteLLM and the AI Hub stack

AI Hub centralizes cloud-model access behind LiteLLM's OpenAI-compatible API. LiteLLM supplies virtual keys, model allow-lists, budgets, rate limits, request auditing, and access to AI Hub privacy controls. AI Hub routes models through OpenRouter; there is no local inference. The review service must use its own restricted LiteLLM virtual key and never receives an OpenRouter credential.

The configured production-style endpoint is `https://rts.ai-hub.center/api/v1`; local AI Hub development can use `http://localhost:4000/v1`. The service appends `/chat/completions`, authenticates with `Authorization: Bearer <LITELLM_API_KEY>`, and selects the gateway alias in `LITELLM_MODEL`. The selected model must support JSON-object responses.

The AI Hub owner operates LiteLLM and its supporting Postgres, Redis, guardrail, audit, and dashboard services. Their internal configuration is outside this repository. This service depends only on the LiteLLM HTTP contract, network access, and its dedicated key/model permissions. Model responses are validated locally before publication; LiteLLM has no Azure credentials and cannot publish reviews itself.

### Azure DevOps boundary

Only the orchestration service receives the Azure DevOps PAT. It discovers accessible projects/repositories, reads exact PR commits and target-branch guidance through REST, and publishes through a dedicated bot identity. The model receives repository identifiers, PR title, approved standards, required context documents, unified diff, and exclusion/coverage metadata as text. It receives no Azure credentials, repository tools, shell, network route, or publishing capability.

## Current request flow

1. At startup, discover repositories visible to the Azure identity. Authenticate webhooks, reject oversized bodies, and ignore unsupported events, undiscovered repositories, inactive PRs, and drafts unless globally enabled. An unknown repository triggers a discovery refresh.
2. Persist and deduplicate a SQLite job, then return promptly to Azure.
3. Re-read current PR state, select the latest PR iteration, and mark stale queued work as superseded.
4. Read all iteration changes and exact old/new file contents. Read `/AGENTS.md` and its direct repository-local Markdown links at the protected target commit; generate the unified diff locally. Linked-document discovery is bounded, non-recursive, and does not crawl source files.
5. Send bounded review context to LiteLLM using the versioned prompt, validate the JSON contract, and verify that findings reference supplied standards and reviewed changed files.
6. Reconcile the iteration-marked PR thread, publish the result and optional status, and record review-run/publication metadata.

Outcomes are `no_violations`, `changes_recommended`, or `review_failed`. Invalid model output, ungrounded findings, missing context, oversized input, and integration failures must never become `no_violations`. Status `succeeded` means the review ran, not that the code is approved.

## Repository layout

```text
architecture-review-service/
├── main.py                         FastAPI app, discovery, lifespan, health, worker startup
├── config.py                       Global settings and runtime repository registry
├── database.py                     Async SQLite connections, queries, transactions
├── integrations/
│   ├── azure_devops/
│   │   ├── router.py               Authenticated JSON webhook and bounded SOAP notification adapter
│   │   ├── client.py               Discovery and repository-bound REST operations
│   │   └── schemas.py              Azure webhook/PR/iteration contracts
│   └── litellm/
│       ├── client.py               Generic JSON chat-completion adapter
│       └── schemas.py              Completion metadata and usage
├── modules/
│   ├── event_ingestion/            Event filtering, jobs, deduplication, retries
│   ├── architecture_review/
│   │   ├── service.py              Worker orchestration and outcome policy
│   │   ├── context.py              Exact diff and protected-context construction
│   │   ├── reviewer.py             Prompt/model harness and grounding validation
│   │   ├── schemas.py              Findings and three-result contract
│   │   ├── repository.py           Metadata-only review-run persistence
│   │   └── prompts/                Versioned review prompts
│   └── publication/                Comment/status reconciliation and ledger
├── migrations/                     Ordered SQL migrations and runner
├── tests/                          Existing contract tests with mocked external HTTP
├── docs/                           Azure integration and company onboarding
├── .env.example                    Complete environment template; no real secrets
├── requirements.txt                Pinned runtime dependencies
├── Dockerfile                      Standalone container build
├── README.md                       Setup, commands, discovery, and repository context
├── RTS_AI_Engineering_Strategy.md  Product/engineering strategy and phased direction
└── research_results.md             Build-versus-adopt research and candidate evaluation
```

Runtime SQLite data belongs in `data/`, normally `data/app.db`, and is not source-controlled. Store only job, review-run, and publication metadata there—not source, diffs, standards, findings, prompts, PATs, or model keys.

Hatchet, PostgreSQL, Langfuse, independent worker containers, and additional agent modules remain later infrastructure phases. The current runtime still uses the in-process worker and shared credentials; the new module boundaries are the preparation for that migration.

## Documentation map

| File | Purpose |
|---|---|
| `README.md` | What the service does, discovery, repository context, and how to run/build/test it |
| `AGENTS.md` | Current implementation, repository map, external boundaries, and working rules |
| `RTS_AI_Engineering_Strategy.md` | Why the capability exists, milestone scope, acceptance criteria, and future phases |
| `research_results.md` | Research evidence, alternatives, trade-offs, and open adopt/build decision |
| `docs/azure-devops-integration.md` | Verified API design and failure/retry semantics |
| `docs/devops-access-request.md` | Company access, webhook, network, and smoke-test guide |
| `.env.example` | Configuration reference and safe example values |

Keep operational setup in `README.md`, implementation context here, strategy in the strategy document, and research in `research_results.md`. Do not duplicate the full AI Hub stack documentation in this repository.

## Working in this repository

- Keep external HTTP in `integrations/`, workflow/business policy in `modules/`, SQL in repositories, and public contracts in schemas. Do not make the model client architecture-review-specific.
- Discover repository metadata through Azure. Do not reintroduce static repository IDs, project names, repository JSON, or context-path lists in `.env`. Only discovered repositories with eligible JSON webhook or SOAP notification events may start reviews.
- Keep LiteLLM and Azure DevOps replaceable behind their existing clients. Do not add direct OpenRouter calls or AI Hub deployment files.
- Never commit `.env`, credentials, source snapshots, rendered runtime prompts, or model responses. Versioned prompt templates belong in `modules/architecture_review/prompts/`. Use separate Azure PAT and LiteLLM virtual-key credentials.
- Add numbered SQL migrations for schema changes; never edit an applied migration. A future fresh-install baseline must preserve upgrade behavior for existing databases.
- Keep reviews fail-closed and advisory. Do not introduce voting, merging, source mutation, required blocking statuses, or model tools.
- When a test is genuinely needed or verification is requested, run `.venv/bin/python -m pytest -q`. The local suite mocks Azure and LiteLLM; passing it does not verify company-server behavior. The suite was not run after the modular multi-repository refactor.
- Company PR `735` verified SOAP created/source-push delivery, exact iterations/diffs, protected target `/AGENTS.md`, DeepSeek through LiteLLM, and Azure publication. Iteration 4 completed automatically on its first attempt with `changes_recommended` in thread `1937`; earlier iterations failed closed on invalid model grounding. Review quality/rubric evaluation remains pending.
- Do not expand this pilot into a general process engine until the OpenHands Agent Canvas and Kodus evaluations and the adopt/adapt/build decision in `research_results.md` are resolved.

## Tests

Tests are not required by default. Do not report missing tests as a violation
and do not recommend them routinely. Suggest tests only when they address a
specific, meaningful regression risk or when a repository standard explicitly
requires them for the change.
