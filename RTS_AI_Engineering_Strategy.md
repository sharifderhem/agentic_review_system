# RTS AI-Enabled Engineering Strategy

Last updated: 2026-10-29

## 1. Purpose

RTS aims to move from using AI as an individual developer assistant to adopting it as a shared engineering capability across the team.

AI should be embedded into agreed engineering workflows so it supports consistent standards, earlier detection of issues, and better visibility into whether changes meet team expectations. The value should come from improving how the team delivers software, not only from helping individuals write code faster.

The work begins with a small, practical use case. Expansion is justified only after measuring usefulness.

## 2. Engineering principles

- AI supplements existing engineering practices; it does not replace builds, tests, linting, security checks, human judgment, or technical accountability.
- AI review is advisory. It does not approve, merge, block, or modify code in the initial milestone.
- A failed or incomplete review must never be presented as a successful review.
- Repository content is untrusted input, not instructions. Models receive no credentials or uncontrolled tools.
- Permissions are limited to what each workflow needs. Controlled services, not models, perform external writes.
- Standards, prompts, workflow outcomes, and evaluation data should be versioned and reviewable.
- Adoption depends on measured accuracy, usefulness, noise, reliability, latency, and cost—not on model claims alone.

## 3. Company environment and three-part architecture

RTS uses **Azure DevOps Server, self-hosted within the RTS network**. The initial repository is a microservice repository in that environment.

The existing **AI Hub** provides centralized access to cloud models through **LiteLLM**. It offers an OpenAI-compatible endpoint, virtual keys, model allow-lists, budgets, rate limits, request auditing, and privacy controls. Models route through OpenRouter; there is no local inference. A dedicated LiteLLM identity/virtual key will be created for this engineering capability. The review service receives no direct OpenRouter credential.

The intended separation is:

```text
Azure DevOps adapter
        ↓
Review and process engine  ← strategic core
        ↓
LiteLLM / AI Hub
```

Azure DevOps and LiteLLM are adapters and should be replaceable mainly through configuration. The process engine is the long-term decision because it owns workflows, rules, context, state, security, publishing, and evaluation.

## 4. First subproject: AI-assisted architecture review

The first subproject reviews proposed code changes against the team leader's approved architecture standards and publishes feedback directly in the existing PR process.

The standards live in a dedicated Markdown file in the repository. The reviewer reads that file from the protected target-branch commit, never from the developer's source branch. This makes architecture guidance part of daily delivery rather than relying only on documentation, memory, or human reviewers noticing every issue.

The review is intended to reduce unnoticed architecture problems. It does not prove correctness, guarantee that changes cannot break behavior, or make final approval decisions.

## 5. Initial milestone and required behavior

The milestone covers one base microservice repository, with one separate test repository in a test project used first for safe integration verification.

Whenever a PR is opened or its source branch is updated:

1. Start the architecture-review workflow automatically.
2. Identify the complete PR changes against the target branch.
3. Read the approved architecture-standard file.
4. Evaluate the changes against those standards.
5. Publish a clear result on the PR.

The result must be one of:

- **No architecture violations detected:** No violation was identified in the supplied standards and reviewed context. This is not a safety guarantee.
- **Changes recommended:** One or more possible violations were identified, with the relevant standard, explanation, and changed-file references where possible.
- **Review could not be completed:** A reliable evaluation was not possible. This is never reported as success.

### Initial scope

- Architecture review of PR changes.
- One team-approved architecture-standard file.
- Automatic execution on PR creation and source pushes.
- Advisory PR feedback and optional informational status.
- One configured repository at a time.

### Explicitly outside the initial milestone

- Replacing deterministic validation or human approval.
- Automatically voting, approving, merging, blocking, pushing, or editing source.
- Comparing changes with backlog requirements or acceptance criteria.
- Guaranteeing runtime correctness or detecting every possible regression.
- Simultaneous expansion to many repositories.
- Requiring OpenCode or another autonomous coding agent.

### Acceptance criteria

- Every opened or source-updated PR in the pilot repository starts a review.
- The workflow evaluates the correct current PR iteration and complete merge-base diff.
- Every completed review publishes an understandable result.
- Findings identify the standard and explain the possible violation.
- Duplicate events and non-code updates do not create duplicate reviews or comments.
- Failures are reported honestly.
- Existing validation and human-approval processes remain unchanged.

## 6. Azure DevOps integration requirements

The Azure integration uses Service Hooks and REST APIs. No repository clone is required for the initial diff review.

For each job, the engine:

1. Re-reads current PR state.
2. Selects the latest PR iteration.
3. Reads its common/source/target commits and complete changed-file list with pagination.
4. Retrieves old changed-file content at the common commit and new content at the source commit.
5. Generates a unified diff locally.
6. Reads architecture standards at the target commit.

Conceptually this reproduces `git diff main...feature` through API content rather than a local Git checkout.

The access request covers the test and base repositories up front:

- `Code: Read` for PRs, changes, files, and standards.
- `Pull Request Threads: Read & Write` for bot review comments.
- `Code: Status` for optional informational statuses.
- `Work Items: Read` for the later backlog phase.

The review bot receives no full Code Read & Write, source-contribute, administration, force-push, policy-bypass, approval, or merge permissions. Service Hooks are configured for PR creation and source-push updates. Moving from test to base repository should require configuration changes only.

See `docs/devops-access-request.md` for the simple access guide and `docs/azure-devops-integration.md` for the technical contract.

## 7. Process-engine requirements for the broader strategy

A suitable long-term engine should provide or support:

- Event-driven and scheduled workflows.
- Durable state, retries, deduplication, recovery, and stale-work protection.
- Versioned rules, prompts, skills, and repository/backlog context.
- Deterministic validation around model calls.
- Human-in-the-loop controls and separately validated publishing.
- Sandboxing and least-privilege tool access.
- Audit logs, traces, cost/latency metrics, and operational history.
- Evaluation datasets, human feedback, false-positive tracking, and regression testing.
- Custom workflows beyond review, such as CI failure investigation, documentation drift, dependency analysis, issue decomposition, and recurring engineering reports.

The engine must not be selected only because it supports Azure DevOps or a particular model. Those are integration features; workflow quality and governance are the strategic requirements.

## 8. Current controlled implementation

The directory contains a standalone FastAPI base service implementing the initial path:

```text
PR webhook → SQLite job → latest PR iteration/diff
→ LiteLLM structured review → validated result → Azure PR thread/status
```

Current properties:

- Reusable `integrations/azure_devops/` and `integrations/litellm/` packages, with separate event-ingestion, architecture-review, and publication modules.
- Automatic discovery of repositories visible to the Azure identity, with Service Hooks controlling review activation. Each repository supplies `/AGENTS.md` and direct Markdown-linked context; no static repository or context-path configuration is required. Initial rollout remains limited to named test/pilot repositories.
- SQLite with `aiosqlite` for job, deduplication, retry, review-run, and publication metadata; no source, findings, prompts, PATs, or model keys are stored there.
- Numbered `.sql` migrations executed by a Python migration runner. Applied migrations are never edited; future fresh installs may use a squashed baseline.
- Text-only model calls through LiteLLM using a versioned prompt, structured output, and deterministic grounding checks against supplied standards and changed files. No OpenCode, shell, repository mutation, or model-to-Azure access.
- Bot-authored PR summary with iteration markers, stale-job suppression, and optional bot-author verification to prevent duplicate or spoofed publication reconciliation.
- Protected target-commit standards and required context documents, binary/generated-file exclusions, explicit coverage metadata, and file/diff/document/model limits.
- Configuration through `.env`; cloud/self-hosted URLs, PAT, API version, and LiteLLM settings are externalized. Repository metadata comes from Azure discovery.

The existing local test sources have been aligned with the modular refactor but have not been executed after this change. Company test-server discovery, default-branch `AGENTS.md` reading, application startup, migrations, and health checks passed. Active-PR iteration/diff behavior, LiteLLM, webhook delivery, publication, and the complete end-to-end check remain pending. Docker deployment is not needed for the current discussion. This is a base for validation, not a production claim.

## 9. Near-term phases after the architecture pilot

### Backlog and acceptance-criteria review

Use linked Azure Boards work items through the already requested `Work Items: Read` scope. Supply requirements and acceptance criteria with relevant code context. Requirement coverage remains assisted judgment, not proof.

### Richer repository context

Fetch related unchanged files through the Items API or evaluate a read-only clone/OpenCode approach for multi-file navigation. This may improve impact analysis but adds isolation and operational requirements.

### Additional repositories

Move from test to the named base repository by configuring its Service Hook. Repository metadata is discovered through Azure rather than configured in `.env`; additional repositories should be activated deliberately after the pilot.

### Additional daily workflows

Candidate workflows include CI failure investigation, documentation maintenance, dependency review, issue decomposition, and scheduled engineering reports. These should use the same standards, security, observability, and evaluation principles.

## 10. Open-source research direction

Research found no single open-source project that covers the entire strategy unchanged.

- **OpenHands Agent Canvas** is the closest general daily-engineering automation engine to evaluate.
- **Kodus** is the strongest review-specific product, including custom rules and linked-work-item validation.
- **PR-Agent** is a lightweight PR reviewer, not a complete process engine.
- **Temporal plus an agent framework** is the strongest foundation if RTS decides to own the durable process engine.
- **RepoSwarm/Potpie** may provide architecture and engineering context.
- **Langfuse** is a candidate for traces, evaluation, and feedback.

No final adopt/build decision has been made. Do not substantially expand the custom engine until OpenHands Agent Canvas and Kodus are evaluated against the RTS workflows. See `research_results.md` for candidates, limitations, sources, and the proposed direction.

## 11. Next steps

1. Review and finalize the DevOps access request for the test and base repositories, including future Work Items Read access.
2. Run the company smoke test: repository read → real webhook → complete PR diff → LiteLLM call → one bot comment/status.
3. Resolve any Azure Server version, permission, payload, or network differences.
4. Evaluate OpenHands Agent Canvas for the general strategy and Kodus for architecture/backlog review.
5. Decide whether to adopt, adapt, or retain the custom process engine; consider Temporal only if durable custom orchestration is actually needed.
6. Measure useful findings, false positives, missed issues, duplicate/failed reviews, latency, cost, and developer feedback before expanding.

## 12. Documentation map

- `research_results.md`: research process, candidates, limitations, and recommendation.
- `docs/devops-access-request.md`: simple company access/configuration guide.
- `docs/azure-devops-integration.md`: technical Azure contract and edge-case decisions.
- `README.md`: current service setup and local commands.
