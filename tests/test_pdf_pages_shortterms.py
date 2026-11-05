"""Short finance terms remain searchable through the public Memory API."""

import asyncio
from types import SimpleNamespace

import pytest

from powercontext.artifacts.models import ArtifactRef, MemoryCitation
from powercontext.sources.pdf_pages import search_pdf_pages


@pytest.mark.parametrize("question, evidence", [("What is EPS?", "EPS"), ("What is net tax?", "net tax")])
def test_short_finance_terms_rank_matching_page(question: str, evidence: str) -> None:
    reference = ArtifactRef(family="memory", artifact_id="synthetic", revision=1)

    def record(number: int, text: str) -> SimpleNamespace:
        citation = MemoryCitation(memory_ref=reference, entry_id=f"page-{number}", entry_version_id=f"version-{number}")
        return SimpleNamespace(
            entry=SimpleNamespace(text=text, entry_id=citation.entry_id, entry_version_id=citation.entry_version_id),
            citation=citation,
        )

    pages = [record(number, "Annual report management and operations") for number in range(30)]
    pages.append(record(31, f"Annual report statement shows {evidence} for the period"))

    class Memory:
        async def search(self, request):
            return SimpleNamespace(hits=())

        async def list(self):
            return SimpleNamespace(entries=tuple(pages))

    result = asyncio.run(search_pdf_pages(Memory(), question, limit=20))
    assert result[0].entry_id == "page-31"
