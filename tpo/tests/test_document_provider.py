from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from github import GithubException

from src.document_provider import (
    GithubDocumentProvider,
    LocalDocumentProvider,
    MissingDocumentError,
    RepositoryNotFoundError,
    build_document_provider,
)
from src.github_loader import DOCUMENT_PRECEDENCE, GitHubDocument


REQUIRED_DOCUMENTS = [
    "AGENTS.md",
    "OPERATING_RULES.md",
    "TPO_SHEETS_SCHEMA.md",
    "TPO_BOOTSTRAP.md",
]


class DocumentProviderTest(unittest.TestCase):
    def test_local_provider_loads_documents_in_precedence_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            for name in REQUIRED_DOCUMENTS:
                (docs_dir / name).write_text(f"# {name}", encoding="utf-8")

            documents = LocalDocumentProvider(docs_dir).load_documents()

            self.assertEqual(list(documents), DOCUMENT_PRECEDENCE)
            self.assertEqual(documents["AGENTS.md"].content, "# AGENTS.md")
            self.assertEqual(documents["AGENTS.md"].provenance.source, "local")
            self.assertTrue(documents["AGENTS.md"].provenance.checksum)

    def test_local_provider_stops_when_document_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            for name in REQUIRED_DOCUMENTS:
                if name != "TPO_BOOTSTRAP.md":
                    (docs_dir / name).write_text(f"# {name}", encoding="utf-8")

            with self.assertRaises(MissingDocumentError) as raised:
                LocalDocumentProvider(docs_dir).load_documents()

            self.assertEqual(raised.exception.document_name, "TPO_BOOTSTRAP.md")

    def test_github_provider_falls_back_to_local_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            for name in REQUIRED_DOCUMENTS:
                (docs_dir / name).write_text(f"# {name}", encoding="utf-8")

            loader = Mock()
            loader.load_documents.side_effect = GithubException(404, "not found")

            provider = GithubDocumentProvider(
                loader=loader,
                fallback=LocalDocumentProvider(docs_dir),
            )
            documents = provider.load_documents()

            self.assertEqual(list(documents), DOCUMENT_PRECEDENCE)
            self.assertEqual(documents["TPO_SHEETS_SCHEMA.md"].content, "# TPO_SHEETS_SCHEMA.md")
            self.assertEqual(documents["TPO_SHEETS_SCHEMA.md"].provenance.source, "local")

    def test_github_provider_reports_repository_not_found_without_fallback(self) -> None:
        loader = Mock()
        loader.load_documents.side_effect = GithubException(404, "not found")

        provider = GithubDocumentProvider(loader=loader, fallback=None)

        with self.assertRaises(RepositoryNotFoundError):
            provider.load_documents()

    def test_build_document_provider_uses_local_source(self) -> None:
        provider = build_document_provider({"document_source": "local"})

        self.assertIsInstance(provider, LocalDocumentProvider)

    def test_github_provider_validates_loaded_documents(self) -> None:
        loader = Mock()
        loader.load_documents.return_value = {
            "AGENTS.md": GitHubDocument("AGENTS.md", "AGENTS.md", "# AGENTS"),
        }

        provider = GithubDocumentProvider(loader=loader, fallback=None)

        with self.assertRaises(MissingDocumentError) as raised:
            provider.load_documents()

        self.assertEqual(raised.exception.document_name, "OPERATING_RULES.md")


if __name__ == "__main__":
    unittest.main()
