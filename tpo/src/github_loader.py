from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from github import Github

from .source_gate import SourceProvenance, build_content_checksum, current_timestamp


DOCUMENT_PRECEDENCE = [
    "OPERATING_RULES.md",
    "TPO_SHEETS_SCHEMA.md",
    "AGENTS.md",
    "TPO_BOOTSTRAP.md",
]


@dataclass(frozen=True)
class GitHubDocument:
    name: str
    path: str
    content: str
    provenance: SourceProvenance | None = None


class GitHubLoader:
    def __init__(
        self,
        repo: str,
        branch: str = "main",
        token: str | None = None,
        cache_dir: str | Path = "data/cache",
    ) -> None:
        self.repo_name = repo
        self.branch = branch
        self.token = token
        self.cache_dir = Path(cache_dir)

    @classmethod
    def from_config(cls, config: dict) -> "GitHubLoader":
        github_config = config.get("github", {})
        token_env = github_config.get("token_env", "GITHUB_TOKEN")
        return cls(
            repo=github_config["repo"],
            branch=github_config.get("branch", "main"),
            token=os.getenv(token_env),
            cache_dir=config.get("cache", {}).get("directory", "data/cache"),
        )

    def load_documents(self, paths: list[str] | None = None) -> dict[str, GitHubDocument]:
        requested_paths = paths or DOCUMENT_PRECEDENCE
        client = Github(self.token) if self.token else Github()
        repo = client.get_repo(self.repo_name)

        documents: dict[str, GitHubDocument] = {}
        for path in requested_paths:
            content_file = repo.get_contents(path, ref=self.branch)
            if isinstance(content_file, list):
                raise ValueError(f"{path} è una directory, atteso un file Markdown.")
            content = content_file.decoded_content.decode("utf-8")
            document = GitHubDocument(
                name=Path(path).name,
                path=path,
                content=content,
                provenance=SourceProvenance(
                    source_type="GITHUB",
                    source_name=Path(path).name,
                    loaded_at=current_timestamp(),
                    read_successfully=True,
                    locator=f"{self.repo_name}:{path}",
                    reference=f"{self.branch}@{getattr(content_file, 'sha', '')}".rstrip("@"),
                    checksum=build_content_checksum(content),
                ),
            )
            documents[document.name] = document
            self._write_cache(document)

        return self.sort_by_precedence(documents)

    def sort_by_precedence(
        self, documents: dict[str, GitHubDocument]
    ) -> dict[str, GitHubDocument]:
        sorted_names = sorted(
            documents,
            key=lambda name: DOCUMENT_PRECEDENCE.index(name)
            if name in DOCUMENT_PRECEDENCE
            else len(DOCUMENT_PRECEDENCE),
        )
        return {name: documents[name] for name in sorted_names}

    def _write_cache(self, document: GitHubDocument) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / document.name
        cache_path.write_text(document.content, encoding="utf-8")
