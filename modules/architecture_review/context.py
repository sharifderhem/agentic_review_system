import difflib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

from config import RepositoryConfig, settings
from integrations.azure_devops.client import AzureDevOpsClient
from integrations.azure_devops.schemas import Iteration, PullRequest


class ReviewFailed(RuntimeError):
    pass


MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class ReviewContext:
    repository_name: str
    repository_id: str
    pull_request_title: str
    standards_path: str
    standards: str
    context_documents: dict[str, str]
    unified_diff: str
    exclusions: list[str]
    reviewable_paths: frozenset[str]
    changed_file_count: int


class ReviewContextBuilder:
    async def build(
        self,
        azure: AzureDevOpsClient,
        repository: RepositoryConfig,
        pr: PullRequest,
        iteration: Iteration,
    ) -> ReviewContext:
        total_context_bytes = 0
        standards = await self._read_required_document(
            azure,
            repository.architecture_standards_path,
            iteration.targetRefCommit.commitId,
            "architecture standards",
        )
        total_context_bytes += len(standards.encode("utf-8"))
        if total_context_bytes > settings.max_total_context_bytes:
            raise ReviewFailed("Combined protected context exceeds the size limit")

        linked_paths = self._linked_document_paths(
            repository.architecture_standards_path, standards
        )
        context_documents: dict[str, str] = {}
        for path in linked_paths:
            if (
                path == repository.architecture_standards_path
                or path in context_documents
            ):
                continue
            if len(context_documents) >= settings.max_context_documents:
                raise ReviewFailed("Required context document count exceeds the limit")
            context_documents[path] = await self._read_required_document(
                azure,
                path,
                iteration.targetRefCommit.commitId,
                "required context document",
            )
            total_context_bytes += len(context_documents[path].encode("utf-8"))
            if total_context_bytes > settings.max_total_context_bytes:
                raise ReviewFailed("Combined protected context exceeds the size limit")

        changes = await azure.get_changes(pr.pullRequestId, iteration.id)
        unified_diff, exclusions, reviewable_paths, changed_file_count = (
            await self._build_diff(azure, changes, iteration)
        )
        return ReviewContext(
            repository_name=repository.name,
            repository_id=repository.repository_id,
            pull_request_title=pr.title,
            standards_path=repository.architecture_standards_path,
            standards=standards,
            context_documents=context_documents,
            unified_diff=unified_diff,
            exclusions=exclusions,
            reviewable_paths=frozenset(reviewable_paths),
            changed_file_count=changed_file_count,
        )

    @staticmethod
    def _linked_document_paths(source_path: str, content: str) -> list[str]:
        paths: list[str] = []
        for match in MARKDOWN_LINK_PATTERN.finditer(content):
            target = match.group(1).strip()
            if not target:
                continue
            if target.startswith("<") and ">" in target:
                target = target[1 : target.index(">")]
            else:
                target = target.split(maxsplit=1)[0]
            try:
                parsed = urlsplit(target)
            except ValueError:
                continue
            if parsed.scheme or parsed.netloc:
                continue
            path = unquote(parsed.path)
            if "\x00" in path or "\\" in path:
                continue
            if not path.lower().endswith((".md", ".markdown")):
                continue
            resolved = ReviewContextBuilder._resolve_link(source_path, path)
            if (
                resolved is not None
                and resolved != source_path
                and resolved not in paths
            ):
                paths.append(resolved)
        return paths

    @staticmethod
    def _resolve_link(source_path: str, target_path: str) -> str | None:
        parts = (
            []
            if target_path.startswith("/")
            else source_path.strip("/").split("/")[:-1]
        )
        for part in target_path.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                if not parts:
                    return None
                parts.pop()
            else:
                parts.append(part)
        return f"/{'/'.join(parts)}" if parts else None

    async def _read_required_document(
        self,
        azure: AzureDevOpsClient,
        path: str,
        commit: str,
        description: str,
    ) -> str:
        content = await azure.get_file_bytes(path, commit)
        if content is None:
            raise ReviewFailed(f"The {description} was not found: {path}")
        if len(content) > settings.max_context_document_bytes:
            raise ReviewFailed(f"The {description} exceeds the size limit: {path}")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReviewFailed(f"The {description} is not UTF-8 text: {path}") from exc

    async def _build_diff(
        self,
        azure: AzureDevOpsClient,
        changes: list[dict[str, Any]],
        iteration: Iteration,
    ) -> tuple[str, list[str], list[str], int]:
        file_changes = [
            change for change in changes if not change.get("item", {}).get("isFolder")
        ]
        if len(file_changes) > settings.max_changed_files:
            raise ReviewFailed(
                f"Changed-file limit exceeded: {len(file_changes)} files"
            )
        file_changes.sort(key=lambda change: change.get("item", {}).get("path", ""))
        sections: list[str] = []
        exclusions: list[str] = []
        reviewable_paths: list[str] = []
        total_bytes = 0
        for change in file_changes:
            item = change.get("item", {})
            path = item.get("path")
            if not path:
                raise ReviewFailed("A changed file has no repository path")
            if self._is_generated(path):
                exclusions.append(f"{path} (generated file)")
                continue
            change_type = str(change.get("changeType", "edit")).lower()
            old_path = change.get("originalPath") or path
            old_bytes = None
            new_bytes = None
            if "add" not in change_type:
                old_bytes = await azure.get_file_bytes(
                    old_path, iteration.commonRefCommit.commitId
                )
            if "delete" not in change_type:
                new_bytes = await azure.get_file_bytes(
                    path, iteration.sourceRefCommit.commitId
                )
            for candidate in (old_bytes, new_bytes):
                if candidate is not None and len(candidate) > settings.max_file_bytes:
                    raise ReviewFailed(f"File size limit exceeded: {path}")
            contents = [candidate for candidate in (old_bytes, new_bytes) if candidate]
            if any(b"\0" in candidate for candidate in contents):
                exclusions.append(f"{path} (binary file)")
                continue
            try:
                old_text = (old_bytes or b"").decode("utf-8")
                new_text = (new_bytes or b"").decode("utf-8")
            except UnicodeDecodeError:
                exclusions.append(f"{path} (non-UTF-8 file)")
                continue
            if old_bytes is None and "add" not in change_type:
                raise ReviewFailed(f"Base content was not found: {old_path}")
            if new_bytes is None and "delete" not in change_type:
                raise ReviewFailed(f"Source content was not found: {path}")
            old_label = f"a{old_path}" if "add" not in change_type else "/dev/null"
            new_label = f"b{path}" if "delete" not in change_type else "/dev/null"
            diff = "\n".join(
                difflib.unified_diff(
                    old_text.splitlines(),
                    new_text.splitlines(),
                    fromfile=old_label,
                    tofile=new_label,
                    lineterm="",
                )
            )
            if diff:
                section = f"## {change_type}: {old_path} -> {path}\n{diff}\n"
                total_bytes += len(section.encode("utf-8"))
                if total_bytes > settings.max_diff_bytes:
                    raise ReviewFailed("Total diff size limit exceeded")
                sections.append(section)
                reviewable_paths.append(path)
        return "\n".join(sections), exclusions, reviewable_paths, len(file_changes)

    @staticmethod
    def _is_generated(path: str) -> bool:
        lowered = path.lower()
        return (
            lowered.endswith((".min.js", ".min.css", ".designer.cs", ".lock"))
            or any(
                segment in lowered
                for segment in ("/generated/", "/dist/", "/build/", "/node_modules/")
            )
        )
