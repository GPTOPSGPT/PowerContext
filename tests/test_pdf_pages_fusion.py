"""Inflected wording can retrieve a page even without an exact FTS hit."""

import asyncio
from types import SimpleNamespace

from powercontext.artifacts.models import ArtifactRef, MemoryCitation
from powercontext.sources.pdf_pages import search_pdf_pages


def test_plural_question_retrieves_singular_page() -> None:
    memory_ref = ArtifactRef(family="memory", artifact_id="fusion-test", revision=1)

    def record(number: int, text: str) -> SimpleNamespace:
        citation = MemoryCitation(memory_ref=memory_ref, entry_id=f"page-{number}", entry_version_id=f"v-{number}")
        return SimpleNamespace(
            entry=SimpleNamespace(text=text, entry_id=citation.entry_id, entry_version_id=citation.entry_version_id),
            citation=citation,
        )

    entries = [record(number, "Annual report operations overview") for number in range(30)]
    entries.append(record(30, "The operating expense increased for the period"))

    class Memory:
        async def search(self, request):
            return SimpleNamespace(hits=())

        async def list(self):
            return SimpleNamespace(entries=tuple(entries))

    result = asyncio.run(search_pdf_pages(Memory(), "What were operating expenses?", limit=20))
    assert any(citation.entry_id == "page-30" for citation in result)
