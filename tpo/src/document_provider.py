from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path

from github import GithubException

from .github_loader import DOCUMENT_PRECEDENCE, GitHubDocument, GitHubLoader


REQUIRED_DOCUMENTS = [
    "AGENTS.md",
    "OPERATING_RULES.md",
    "TPO_SHEETS_SCHEMA.md",
    "TPO_BOOTSTRAP.md",
]


class MissingDocumentError(RuntimeError):
    def __init__(self, document_name: str) -> None:
        self.document_name = document_name
        super().__init__(f"Documento mancante:\n{document_name}")


class RepositoryNotFoundError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Repository GitHub non trovato")


class DocumentProvider(ABC):
    @abstractmethod
    def load_documents(self) -> dict[str, GitHubDocument]:
        """Load official TPO documents using the provider source."""

    def _validate_documents(
        self, documents: dict[str, GitHubDocument]
    ) -> dict[str, GitHubDocument]:
        for document_name in REQUIRED_DOCUMENTS:
            if document_name not in documents:
                raise MissingDocumentError(document_name)
        return self._sort_by_precedence(documents)

    def _sort_by_precedence(
        self, documents: dict[str, GitHubDocument]
    ) -> dict[str, GitHubDocument]:
        sorted_names = sorted(
            documents,
            key=lambda name: DOCUMENT_PRECEDENCE.index(name)
            if name in DOCUMENT_PRECEDENCE
            else len(DOCUMENT_PRECEDENCE),
        )
        return {name: documents[name] for name in sorted_names}


class LocalDocumentProvider(DocumentProvider):
    def __init__(self, docs_dir: str | Path = "docs") -> None:
        self.docs_dir = Path(docs_dir)

    def load_documents(self) -> dict[str, GitHubDocument]:
        documents: dict[str, GitHubDocument] = {}
        for document_name in REQUIRED_DOCUMENTS:
            path = self.docs_dir / document_name
            if not path.exists():
                raise MissingDocumentError(document_name)
            documents[document_name] = GitHubDocument(
                name=document_name,
                path=str(path),
                content=path.read_text(encoding="utf-8"),
            )
        return self._validate_documents(documents)

    def has_all_documents(self) -> bool:
        return all((self.docs_dir / document_name).exists() for document_name in REQUIRED_DOCUMENTS)


class GithubDocumentProvider(DocumentProvider):
    def __init__(self, loader: GitHubLoader, fallback: LocalDocumentProvider | None = None) -> None:
        self.loader = loader
        self.fallback = fallback

    @classmethod
    def from_config(cls, config: dict) -> "GithubDocumentProvider":
        return cls(
            loader=GitHubLoader.from_config(config),
            fallback=LocalDocumentProvider(),
        )

    def load_documents(self) -> dict[str, GitHubDocument]:
        try:
            documents = self.loader.load_documents(REQUIRED_DOCUMENTS)
            return self._validate_documents(documents)
        except GithubException as exc:
            if self.fallback and self.fallback.has_all_documents():
                print("[INFO] GitHub non disponibile.", file=sys.stderr)
                print("[INFO] Utilizzo documentazione locale.", file=sys.stderr)
                return self.fallback.load_documents()
            if getattr(exc, "status", None) == 404:
                raise RepositoryNotFoundError() from exc
            raise RuntimeError(f"GitHub non disponibile: {exc}") from exc


def build_document_provider(config: dict) -> DocumentProvider:
    source = str(config.get("document_source", "github")).strip().lower()
    if source == "local":
        return LocalDocumentProvider()
    if source == "github":
        return GithubDocumentProvider.from_config(config)
    raise ValueError("document_source deve essere 'local' oppure 'github'.")
