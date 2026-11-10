from integrations.azure_devops.schemas import (
    AzureCommit,
    AzureRepository,
    Iteration,
    PullRequest,
)
from integrations.litellm.schemas import JSONCompletion
from modules.architecture_review.schemas import ReviewOutcome, ReviewResult


def make_event(event_id="event-1", commit="source-1", **resource_overrides):
    resource = {
        "repository": {"id": "repo-1"},
        "pullRequestId": 22,
        "status": "active",
        "isDraft": False,
        "lastMergeSourceCommit": {"commitId": commit},
        **resource_overrides,
    }
    return {
        "id": event_id,
        "eventType": "git.pullrequest.created",
        "resource": resource,
    }


class FakeAzure:
    def __init__(self):
        self.pr = PullRequest(
            pullRequestId=22,
            status="active",
            title="Improve orders",
            supportsIterations=True,
            sourceRefName="refs/heads/feature",
            targetRefName="refs/heads/main",
            repository=AzureRepository(id="repo-1"),
        )
        self.iteration = Iteration(
            id=1,
            sourceRefCommit=AzureCommit(commitId="source-1"),
            commonRefCommit=AzureCommit(commitId="base-1"),
            targetRefCommit=AzureCommit(commitId="target-1"),
        )
        self.changes = [
            {
                "changeTrackingId": 1,
                "changeType": "edit",
                "item": {"path": "/src/orders.py", "isFolder": False},
            }
        ]
        self.files = {
            ("base-1", "/src/orders.py"): b"def handler():\n    return 1\n",
            ("source-1", "/src/orders.py"): b"def handler():\n    return 2\n",
            ("target-1", "/AGENTS.md"): b"ARCH-01: Keep handlers thin.",
        }
        self.threads = []
        self.statuses = []

    def for_repository(self, repository):
        return self

    async def get_pull_request(self, pull_request_id):
        return self.pr

    async def get_iterations(self, pull_request_id):
        return [self.iteration]

    async def get_changes(self, pull_request_id, iteration_id):
        return self.changes

    async def get_file_bytes(self, path, commit):
        return self.files.get((commit, path))

    async def find_thread(self, pull_request_id, marker):
        for thread in self.threads:
            if marker in thread["content"]:
                return thread["id"]
        return None

    async def create_thread(self, pull_request_id, content):
        thread_id = len(self.threads) + 1
        self.threads.append({"id": thread_id, "content": content})
        return thread_id

    async def create_status(self, pull_request_id, iteration_id, state, description):
        self.statuses.append((iteration_id, state, description))


class FakeLiteLLM:
    def __init__(self, result=None, error=None):
        self.result = result or ReviewResult(
            outcome=ReviewOutcome.NO_VIOLATIONS,
            summary="The changed handler remains thin.",
        )
        self.error = error
        self.calls = []

    async def complete_json(self, *, system_prompt, input_data, model):
        self.calls.append(
            {
                "unified_diff": input_data["unified_diff"],
                "exclusions": input_data["coverage"]["excluded_files"],
            }
        )
        if self.error:
            raise self.error
        return JSONCompletion(
            content=self.result.model_dump(mode="json"),
            model=model,
        )
