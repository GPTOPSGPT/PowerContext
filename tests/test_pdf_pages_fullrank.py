"""Synthetic proof that a citable page outside FTS candidates can be found."""

import asyncio
from types import SimpleNamespace

from powercontext.artifacts.models import ArtifactRef, MemoryCitation
from powercontext.sources.pdf_pages import search_pdf_pages


def test_full_corpus_ranks_evidence_outside_fts_candidates() -> None:
    reference = ArtifactRef(family="memory", artifact_id="synthetic", revision=1)

    def record(number: int, text: str) -> SimpleNamespace:
        citation = MemoryCitation(memory_ref=reference, entry_id=f"page-{number}", entry_version_id=f"version-{number}")
        return SimpleNamespace(
            entry=SimpleNamespace(text=text, entry_id=citation.entry_id, entry_version_id=citation.entry_version_id),
            citation=citation,
        )

    pages = [record(number, "Acme annual report company operations and management discussion") for number in range(30)]
    pages.append(record(31, "Cash flow statement records capital expenditures, depreciation and amortization."))

    class Memory:
        async def search(self, request):
            return SimpleNamespace(hits=())

        async def list(self):
            return SimpleNamespace(entries=tuple(pages))

    result = asyncio.run(search_pdf_pages(Memory(), "What are capex and D&A from cash flow?", limit=5))
    assert result[0].entry_id == "page-31"
    assert len(result) == 5
