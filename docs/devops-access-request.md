# Azure DevOps access request — simple guide

## What we need from DevOps

This is **configuration and access setup only**. DevOps does not need to write or install application code.

We need access to two named repositories from the beginning:

1. **One private test repository in a test project**, containing synthetic code only. We use it to verify the integration safely.
2. **One named base repository** for the first real architecture-review pilot.

Requesting both now avoids another access request when we move from testing to the pilot. The implementation automatically discovers repositories visible to the Azure identity, while Service Hooks control which repositories activate reviews. Rollout and access should remain limited to named repositories.

## 1. Review bot account and PAT

The **review bot account** is the Azure DevOps identity that publishes PR comments. It is not a human user's account.

The **PAT (Personal Access Token)** is the secret our service uses to authenticate as that bot. The AI model produces review text, but it never receives this PAT. Only our controlled service uses it.

Approximate GitHub equivalent: a bot account with a fine-grained PAT.

**Request:** A dedicated non-human identity with access only to the two named repositories and a PAT containing only the scopes below.

## 2. `Code: Read` — `vso.code`

**What it does:** Reads Git repository and PR information without changing it.

**What we use it for:**

- PR metadata and source/target commits.
- PR iterations and changed-file lists.
- Old and new versions of changed files.
- The architecture-standard `.md` file from the protected target commit.

Approximate GitHub equivalent: **Contents: Read**, together with PR read access.

It does not allow pushing commits, changing branches, or modifying the standards file. Automatic project/repository discovery also requires read access to project metadata, normally the `Project and Team: Read` (`vso.project`) scope.

## 3. `Pull Request Threads: Read & Write` — `vso.threads_full`

**What it does:** Reads and writes PR discussion threads and comments.

**What we use it for:**

- Checking whether our review was already posted, preventing duplicates.
- Publishing the architecture review as a bot comment on the PR.

Approximate GitHub equivalent: **Pull requests: Read & write** for review comments.

This permission concerns PR discussions; it is not permission to change source code or merge the PR.

## 4. `Code: Status` — `vso.code_status`

**What it does:** Publishes a small informational status on a PR or PR iteration.

**What we use it for:** Displaying states such as `Review running`, `Changes recommended`, or `Review could not be completed`.

Approximate GitHub equivalent: a commit status or check result.

Our status is advisory only. It must not be configured as a required status that blocks merging. The review can work with comments alone, but we request this now to avoid another permission request later.

## 5. `Work Items: Read` — `vso.work`

**What it does:** Reads Azure Boards work items.

**What we will use it for in a later phase:** Reading the user story, requirements, and acceptance criteria linked to a PR, then comparing them with the implementation.

Approximate GitHub equivalent: **Issues: Read**.

This is not used by the first architecture-review phase, but we request it now for the agreed backlog phase.

## 6. Service Hooks

A **Service Hook** tells Azure DevOps to send an HTTPS notification to our service when an event happens. It is configuration, not code installed in Azure DevOps.

Approximate GitHub equivalent: repository webhooks.

Configure these for both named repositories:

- **Pull request created** — starts the initial review. Similar to GitHub's `pull_request.opened` event.
- **Pull request updated**, filtered to **`PushNotification`** — starts a review when the source branch receives new commits. Similar to GitHub's `pull_request.synchronize` event.

The `PushNotification` filter avoids reviews when only reviewers, votes, or PR status change.

**Target URL:** `https://{review-service-host}/webhooks/azure-devops`

Configure Basic authentication using the separate webhook credentials we provide. Do not use the Azure PAT as the webhook password or place secrets in the URL.

**Where:** Project settings → Service hooks → Create subscription → Web Hooks.

## 7. Network and TLS

Only these connections are required:

| Source | Destination | Purpose |
|---|---|---|
| Azure DevOps | Review service HTTPS endpoint | Deliver PR events |
| Review service | Azure DevOps HTTPS endpoint | Read PR/work-item data and post comments/statuses |
| Review service | LiteLLM HTTPS endpoint | Request the AI review |

No SSH, repository-clone access, inbound LiteLLM connection, or model-to-Azure connection is required.

If the company uses an internal certificate authority, provide its public CA bundle. We will configure it with `AZURE_DEVOPS_CA_BUNDLE`; TLS verification will not be disabled.

Also confirm the Azure DevOps Server version so we can select a supported `AZURE_DEVOPS_API_VERSION`.

## 8. Separate LiteLLM credential

The AI Hub owner provides a **dedicated LiteLLM virtual key**, restricted to the selected review model with budget and rate limits.

This is separate from the Azure PAT:

- **Azure PAT:** read Azure information and publish PR feedback.
- **LiteLLM key:** request the model review through AI Hub.

The service receives no direct OpenRouter credential.

## Permissions we do not request

- Full Code Read & Write.
- Source push, branch modification, force push, or policy bypass.
- PR voting, approval, completion, or merge permission.
- Project/collection, pipeline, or Service Hook administration for the bot account.
- Access to unrelated repositories.

A project administrator may be needed to create the Service Hooks, but that administrator permission is not given to the review bot.

## Smoke test

1. Confirm the bot can read the test repository but cannot push or modify it.
2. Run the Service Hook Test and inspect its delivery history.
3. Open a test PR and verify one model call and one bot comment.
4. Push to the source branch and verify one review for the new iteration.
5. Change a reviewer or vote and verify no new review for the same source commit.
6. Replay a webhook and verify no duplicate comment.
7. Verify technical failures say **Review could not be completed**, never **No violations**.
8. Verify the architecture `.md` file is read from the protected target commit.
9. Revoke/rotate the PAT and LiteLLM key and confirm access fails closed.

## Official sources and design note

The permission meanings, event types, and API behavior above come from Microsoft documentation:

- [Personal access tokens](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops)
- [Repository permissions](https://learn.microsoft.com/en-us/azure/devops/repos/git/set-git-repository-permissions?view=azure-devops)
- [Service Hook events](https://learn.microsoft.com/en-us/azure/devops/service-hooks/events?view=azure-devops)
- [Web Hook configuration](https://learn.microsoft.com/en-us/azure/devops/service-hooks/services/webhooks?view=azure-devops)
- [PR Threads API](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/create?view=azure-devops-rest-7.1)
- [PR statuses](https://learn.microsoft.com/en-us/azure/devops/repos/git/pull-request-status?view=azure-devops)

The two-repository rollout, least-privilege combination, and GitHub comparisons are our recommended design and approximate analogies—not Microsoft-mandated setup or exact one-to-one product equivalents.
