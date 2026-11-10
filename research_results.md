# Research results — Azure integration and AI engineering engines

Last updated: 2026-10-29

## 1. What we researched and why

The research began with a narrow question: can RTS automatically review architecture standards on PRs in its self-hosted Azure DevOps Server and publish advisory comments through a dedicated bot?

It then expanded to a broader build-versus-adopt question: should RTS maintain its own review/process engine, or use an existing open-source engine for AI-enabled daily engineering work?

The final evaluation treated Azure DevOps and LiteLLM as pluggable adapters. The priority was the engine itself: workflow orchestration, rules/context, durability, human controls, sandboxing, safe publishing, observability, evaluation, and support for workflows beyond PR review.

Research included:

1. Microsoft documentation for Service Hooks, PATs, PR iterations/changes, file content, comments, statuses, permissions, retries, and cloud/self-hosted URL differences.
2. Free ways to test the Azure integration without consuming an Azure trial.
3. Open-source AI PR reviewers with Azure DevOps support.
4. General AI engineering automation platforms, durable workflow engines, agent frameworks, context providers, and observability/evaluation tools.

This was documentary research using official project repositories and documentation where possible. It was not hands-on benchmarking, a security audit, or proof of compatibility with the company server. Self-hosting a reviewer and supporting self-hosted Azure DevOps Server are separate claims; the latter still needs an RTS smoke test.

## 2. Azure DevOps findings

The required integration is supported through Service Hooks and REST APIs:

- Use `git.pullrequest.created` and `git.pullrequest.updated` with the `PushNotification` filter.
- Use a dedicated bot PAT with Code Read, PR Threads Read & Write, optional Code Status, and Work Items Read for the later backlog phase.
- Read the latest PR iteration and paginate Iteration Changes. The default comparison uses the common commit of source and target.
- Retrieve old/new changed-file content at exact commits with Items Get and generate unified diffs locally. A full clone is unnecessary for the initial review.
- Publish one bot-authored summary through PR Threads and optionally an iteration-scoped informational status.
- Expect duplicate webhook deliveries and non-code PR updates; deduplicate by event and source commit and reconcile comments using an iteration marker.
- Keep model and publishing privileges separate. Only the controlled service receives the PAT.

Microsoft's documentation also confirms transient Service Hook retries and why the receiver should persist work quickly rather than perform a model call inside the webhook request.

For no-card testing, a new cloud Azure DevOps organization now requires an active Azure subscription. **Azure DevOps Server Express** is free for up to five active users and supports the same features as Server, but it requires a Windows installation. The practical company path remains a disposable test repository followed by the named base repository.

Primary sources: [Service Hook events](https://learn.microsoft.com/en-us/azure/devops/service-hooks/events?view=azure-devops), [Web Hooks](https://learn.microsoft.com/en-us/azure/devops/service-hooks/services/webhooks?view=azure-devops), [delivery troubleshooting](https://learn.microsoft.com/en-us/azure/devops/service-hooks/troubleshoot?view=azure-devops), [PATs](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops), [Iterations](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-iterations/list?view=azure-devops-rest-7.1), [Iteration Changes](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-iteration-changes/get?view=azure-devops-rest-7.1), [Items](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/items/get?view=azure-devops-rest-7.1), [Threads](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/create?view=azure-devops-rest-7.1), and [Server Express downloads](https://learn.microsoft.com/en-us/azure/devops/server/download/azuredevopsserver?view=azure-devops).

## 3. Review-specific open-source candidates

### Kodus

**What it is:** A team-oriented, self-hostable AI code-review product with PR automation and operational controls.

**Relevant strengths:** Azure DevOps webhooks and PR comments, custom natural-language rules, architecture/repository context, severity controls, token visibility, technical-debt/delivery metrics, and business-logic validation against linked work items. It supports OpenAI-compatible endpoints, so a LiteLLM connection may be possible.

**Limitations:** Primarily review-focused rather than a general engineering automation engine. It is a larger platform than the custom pilot and uses dual AGPL/enterprise licensing; every required feature must be checked against those terms.

**Assessment:** Closest existing product for architecture review plus the future backlog phase.

Sources: [repository](https://github.com/kodustech/kodus-ai), [Azure DevOps setup](https://docs.kodus.io/en/knowledge_base/how-to-set-up-ai-code-review-on-azure-devops), [license](https://github.com/kodustech/kodus-ai/blob/main/license.md).

### PR-Agent

**What it is:** A mature open-source PR review and suggestion agent.

**Relevant strengths:** Azure DevOps support, CLI/Docker/webhook deployment, LiteLLM model support, custom prompts, repository context files such as `best_practices.md`, large-PR compression, and an active community. Current license is MIT.

**Limitations:** It is a reviewer, not a durable general process platform. It does not provide the same native Azure Boards direction or RTS's exact three-result contract without customization.

**Assessment:** Best lightweight candidate for a LiteLLM + standards-file pilot, but not the recommended long-term strategic core.

Sources: [repository](https://github.com/The-PR-Agent/pr-agent), [custom context and best practices](https://docs.pr-agent.ai/tools/improve/).

### AI Review

**What it is:** A configurable AI reviewer supporting inline, summary, context, reply, and agent modes.

**Relevant strengths:** Azure DevOps support, customizable prompts/policies, OpenAI-compatible endpoint configuration, multiple providers, repository exploration through an optional agent mode, Docker/CI use, and Apache-2.0 licensing.

**Limitations:** More pipeline-oriented than the persistent RTS webhook worker. No documented Azure Boards requirements workflow. Agent shell access would need strict restriction.

**Assessment:** Useful alternative if agentic repository exploration becomes important.

Source: [repository](https://github.com/Nikita-Filonov/ai-review).

### Azure DevOps AI Code Review extension

**What it is:** A native Azure DevOps pipeline task using Azure OpenAI.

**Relevant strengths:** PR summaries/feedback, additional prompts, file exclusions, and MIT licensing.

**Limitations:** Azure OpenAI-specific, no backlog integration, limited process/security/output control, and a smaller/older project than the leading options.

**Assessment:** A useful native integration reference, not a close fit for AI Hub or the broader strategy.

Source: [repository](https://github.com/tlaukkanen/azure-devops-ai-code-review).

### Azure DevOps SkillFlow

**What it is:** A pipeline task running Markdown-defined LangGraph skills with selectable Azure DevOps tools.

**Relevant strengths:** Interesting match for versioned engineering skills and controlled tool selection.

**Limitations:** The repository had no declared license when checked, so source availability should not be treated as permission to adopt it as open source.

**Assessment:** Interesting architecture, but excluded from open-source recommendation until licensing is clarified.

Source: [repository](https://github.com/simonebittidev/azure-devops-skillflow).

## 4. General engineering automation and agent platforms

### OpenHands Agent Canvas

**What it is:** A self-hosted control center for coding agents and scheduled/event-driven automations, not merely an issue resolver.

**Relevant strengths:** Scheduled and webhook automations, prebuilt/custom workflows, run history, multiple repositories, agent and LLM profiles, multiple backends, Docker isolation, and support for several agent runtimes. Deterministic script bundles can handle polling, deduplication, and fixed API calls while reserving AI for judgment. The main project and automation service are MIT-licensed.

**Limitations:** RTS still needs a proper Azure DevOps adapter, exact result contracts, safe-publishing verification, and evaluation. Broad agent permissions require careful sandboxing. The newer automation stack has less operational history than Temporal.

**Assessment:** Closest existing engine to the general goal of AI embedded in daily engineering work. Evaluate first for the broader strategy.

Sources: [OpenHands](https://github.com/OpenHands/OpenHands), [automation documentation](https://docs.openhands.dev/openhands/usage/agent-canvas/prebuilt-automations), [automation service](https://github.com/OpenHands/automation).

### OpenHands issue resolver

**What it is:** The narrower Azure DevOps issue/PR resolver within the OpenHands ecosystem.

**Relevant strengths:** Azure DevOps issue handling, PR comment responses, custom repository instructions, and configurable model base URL.

**Limitations:** Designed to change code and create branches/PRs. Its documented Azure setup requests Code and Work Items Read & Write, which conflicts with the initial read-only review model.

**Assessment:** Relevant to later controlled implementation workflows, not the restricted first milestone.

Source: [resolver documentation](https://github.com/OpenHands/OpenHands/blob/main/openhands/resolver/README.md).

## 5. Durable workflow and agent frameworks

### Temporal

**What it is:** A durable execution platform for reliable workflows, not an AI product.

**Relevant strengths:** Crash recovery, retries, durable state/timers/schedules, human signals and approval waits, long-running workflows, controlled activities, and operational maturity. MIT-licensed, with an official LangGraph integration.

**Limitations:** No built-in architecture rules, AI review, backlog context, prompt management, or evaluation product. It requires custom capabilities and more infrastructure than the pilot needs.

**Assessment:** Strongest foundation if RTS decides to own the long-term process engine rather than adopt one.

Sources: [repository](https://github.com/temporalio/temporal), [durable execution](https://docs.temporal.io/evaluate/why-temporal), [LangGraph integration](https://docs.temporal.io/develop/python/integrations/langgraph).

### LangGraph

**What it is:** A low-level framework for stateful agents and long-running workflows.

**Relevant strengths:** Durable execution, human-in-the-loop, memory, and controlled agent state. It can run inside Temporal.

**Limitations:** It does not supply the complete engineering product, Azure/backlog workflows, governance UI, or evaluation program.

**Assessment:** Strong agent-level companion to a durable process engine.

Source: [repository](https://github.com/langchain-ai/langgraph).

### Microsoft Agent Framework

**What it is:** Microsoft's open framework for production agents and multi-agent workflows in Python and .NET.

**Relevant strengths:** Graph orchestration, checkpointing, human-in-the-loop, declarative agents/skills, provider flexibility, and OpenTelemetry. The .NET support may be relevant to RTS microservices.

**Limitations:** Younger than some alternatives and still requires the surrounding process engine, connectors, publishing boundaries, and evaluation.

**Assessment:** A serious agent-framework candidate, especially for a mixed Python/.NET engineering organization.

Source: [repository](https://github.com/microsoft/agent-framework).

### CrewAI

**What it is:** A high-level multi-agent and event-driven workflow framework.

**Relevant strengths:** Role-based crews, deterministic flows, structured outputs, checkpointing, human input, and MIT licensing.

**Limitations:** Stronger control-plane, governance, and observability features are associated with the commercial AMP offering. It is not an engineering platform by itself.

**Assessment:** Useful for specialized multi-agent tasks, not the preferred sole RTS engine.

Source: [repository](https://github.com/crewAIInc/crewAI).

### Windmill

**What it is:** A code-first platform for scripts, workflows, apps, schedules, approvals, and AI agents.

**Relevant strengths:** Webhooks/schedules, approval steps, isolated workers, sandboxing, Git sync, environment promotion, and self-hosted administration.

**Limitations:** Not engineering-specific; PR/backlog context and agent evaluation remain custom. AGPL and commercial-edition boundaries need review.

**Assessment:** A credible Temporal alternative when built-in workflow administration and UI matter.

Source: [repository](https://github.com/windmill-labs/windmill).

### n8n

**What it is:** A visual AI/workflow automation platform with many integrations and approval patterns.

**Relevant strengths:** Visual orchestration, custom code, self-hosting, and a broad integration ecosystem.

**Limitations:** It is fair-code under the Sustainable Use License rather than a conventional open-source license, and is less specialized for durable engineering-agent workflows.

**Assessment:** Possible for auxiliary automation, not a first choice for the RTS engine.

Source: [repository](https://github.com/n8n-io/n8n).

## 6. Engineering context providers

### RepoSwarm

**What it is:** A multi-repository architecture discovery platform producing standardized `.arch.md` documents.

**Relevant strengths:** Incremental repository analysis, architecture context for agents/onboarding, Temporal workflows, and LiteLLM/Azure DevOps support.

**Limitations:** It generates architecture knowledge; it is not the general process engine.

**Assessment:** Useful when RTS wants living architecture context beyond one manually maintained standards file.

Source: [repository](https://github.com/reposwarm/reposwarm).

### Potpie

**What it is:** A context graph for AI-native software development.

**Relevant strengths:** Indexes code, history, decisions, team knowledge, issues, reviews, and workflows to support project-specific planning/debugging. Integrates with several coding harnesses and uses Apache-2.0 licensing.

**Limitations:** Context provider rather than durable workflow engine.

**Assessment:** Relevant to deeper architecture and organizational-knowledge reviews.

Source: [repository](https://github.com/potpie-ai/potpie).

## 7. Security and evaluation references

### GitHub Agentic Workflows

**What it is:** Markdown/YAML-defined agentic automation for daily repository work.

**Relevant strengths:** PR review, issue triage, CI investigation, documentation, dependency analysis, and reports. Agents are read-only and sandboxed by default; configured writes pass through validated `safe-outputs` jobs.

**Limitations:** Deeply coupled to GitHub Actions.

**Assessment:** Not the RTS engine, but an excellent reference for the required read-only-agent + separately-validated-publisher security pattern.

Source: [repository](https://github.com/githubnext/gh-aw).

### Langfuse

**What it is:** An open LLM/agent observability and evaluation platform.

**Relevant strengths:** Traces, prompt versioning, datasets, regression tests, human labels/feedback, automated evaluators, and debugging.

**Limitations:** It does not orchestrate engineering work.

**Assessment:** Strong companion for determining whether AI workflows are accurate and improving before expansion.

Source: [repository](https://github.com/langfuse/langfuse).

## 8. Overall findings and recommended direction

No candidate covers the whole strategy unchanged. Review quality alone is not enough: the strategic engine is the combination of workflow orchestration, engineering context, safe publishing, and evaluation.

Recommended evaluation order:

1. **OpenHands Agent Canvas** for general daily engineering automation.
2. **Kodus** for architecture and linked-work-item review.
3. **PR-Agent** only if a lightweight PR reviewer is sufficient.
4. **Temporal + LangGraph or Microsoft Agent Framework** if RTS decides to own the durable process engine.
5. **RepoSwarm/Potpie** later for richer context and **Langfuse** for measurement before scaling.

The existing small FastAPI service remains a controlled architecture-review pilot and integration reference. It should not be expanded into a general platform until these options are evaluated. The final adopt/adapt/build decision remains open.
