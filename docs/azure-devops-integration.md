# Azure DevOps integration contract

This service uses the same REST resources with Azure DevOps Services and Azure DevOps Server. The base URL already includes either the cloud organization (`https://dev.azure.com/{organization}`) or the self-hosted collection (`https://{server}/{collection}`). Base URL, PAT, and API version are environment configuration; project/repository metadata is discovered through REST. The initial implementation uses `7.1`; the company server must be checked for its supported version.

## Events and authentication

Configure project Web Hooks for:

- `git.pullrequest.created`.
- `git.pullrequest.updated`, preferably filtered to `PushNotification` and the pilot repository.

The updated event also represents reviewer, vote, and status changes. The service therefore deduplicates by repository, pull request, and source commit in addition to the event ID. It accepts only active PRs in repositories discovered through the Azure identity; drafts are skipped by global default. Discovery alone does not activate reviews—the repository must also have an eligible Service Hook event.

The webhook requires HTTP Basic authentication and rejects bodies over 2 MB. HTTPS remains the production recommendation; the isolated internal test environment may use HTTP. It returns quickly after persisting a job. Azure retries HTTP 408/502/503/504 up to eight times before probation behavior, so duplicate delivery is expected and supported. Do not return 410 unless permanently retiring the subscription: 410 disables it.

Sources: [Web Hooks](https://learn.microsoft.com/en-us/azure/devops/service-hooks/services/webhooks?view=azure-devops), [event reference](https://learn.microsoft.com/en-us/azure/devops/service-hooks/events?view=azure-devops), [delivery troubleshooting](https://learn.microsoft.com/en-us/azure/devops/service-hooks/troubleshoot?view=azure-devops).

## Reading the exact PR changes

For each job the worker:

1. Calls Pull Requests Get and confirms repository/active/draft state.
2. Calls Iterations List and selects the highest iteration ID.
3. Calls Iteration Changes Get with default `compareTo=0`, which compares against the common commit of source and target. It follows `nextSkip` until all pages are read.
4. Reads base content at the iteration's `commonRefCommit`, new content at `sourceRefCommit`, and trusted architecture standards plus required context documents at `targetRefCommit`.
5. Generates unified diffs locally and supplies explicit coverage/exclusion metadata. No clone, merge, checkout, shell, or repository write is needed.

The Diffs API also exposes merge-base comparisons, but returns change metadata rather than the textual patch required by this reviewer. Items/Get supplies exact file bytes at a commit.

Sources: [PR Get](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-requests/get-pull-request-by-id?view=azure-devops-rest-7.1), [Iterations List](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-iterations/list?view=azure-devops-rest-7.1), [Iteration Changes](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-iteration-changes/get?view=azure-devops-rest-7.1), [Diffs Get](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/diffs/get?view=azure-devops-rest-7.1), [Items Get](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/items/get?view=azure-devops-rest-7.1).

## Publishing

A single PR summary thread contains a hidden iteration marker. Before posting, the service lists threads and reconciles an existing marker; it also persists publication state. This covers retries and a crash after Azure accepts a comment but before the local database is updated.

An optional iteration status uses `pending`, `succeeded` for either completed review outcome, and `error` for technical failure. It is informational only; no required branch status policy should be created. `succeeded` means the review ran, not that the code is approved.

Sources: [Threads List](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/list?view=azure-devops-rest-7.1), [Threads Create](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/create?view=azure-devops-rest-7.1), [PR statuses](https://learn.microsoft.com/en-us/azure/devops/repos/git/pull-request-status?view=azure-devops), [Statuses Create](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-statuses/create?view=azure-devops-rest-7.1).

## Reliability and scope decisions

- A newer iteration makes older queued work harmless: every job reads current state, stale jobs become `superseded`, and only one publication is allowed per iteration.
- Adds, edits, deletes, and renames use exact commits and `originalPath` where provided.
- Standards (default `/AGENTS.md`), configured context documents, and direct repository-local Markdown links from the standards file are required from the protected target commit. Link discovery is non-recursive and does not crawl source files. Document-count, per-document, and combined-context limits are enforced.
- Binary, non-UTF-8, and common generated files are listed to the model as exclusions. File-count, per-file, total-diff, webhook, model-output, and execution-time limits are configured.
- Oversized input, missing standards/content, unsupported iterations, Azure errors, model errors, invalid model JSON, and findings that reference unknown standards or unreviewed files can never become `no_violations`.
- Review results are `no_violations`, `changes_recommended`, or `review_failed`. Findings are required only for `changes_recommended`.
- The model receives no PAT, Git credentials, tools, shell, network route, or publishing ability. Only the orchestration service calls Azure.
- Logs contain job/PR/iteration identifiers and safe error categories, not credentials, source, diffs, standards, or prompts.

Company test-server project/repository discovery and default-branch `AGENTS.md` reading succeeded with API `7.1`. Active-PR iteration/diff behavior, webhook delivery, LiteLLM, publication, and the complete on-premises smoke test remain pending.
