"""Synthetic relevance check for page-level financial evidence retrieval."""

import asyncio
from types import SimpleNamespace

from powercontext.artifacts.models import ArtifactRef
from powercontext.sources.pdf_pages import search_pdf_pages


def test_multiconcept_evidence_outranks_repeated_boilerplate() -> None:
    reference = ArtifactRef(family="memory", artifact_id="synthetic-pdf", revision=1)
    noise = [
        SimpleNamespace(
            memory_ref=reference,
            entry_id=f"boilerplate-{number}",
            entry_version_id=f"version-{number}",
            text="The annual report describes operating activities and regional operations.",
        )
        for number in range(20)
    ]
    evidence = SimpleNamespace(
        memory_ref=reference,
        entry_id="evidence-page",
        entry_version_id="evidence-version",
        text="Regional operating income and capital expenditures are reported in this table.",
    )

    class Memory:
        def __init__(self) -> None:
            self.queries = []

        async def search(self, request):
            self.queries.append(request.query)
            return SimpleNamespace(hits=(*noise, evidence))

    memory = Memory()
    result = asyncio.run(search_pdf_pages(memory, "Which regions report operating income and capital expenditures?", 3))

    assert result[0].entry_id == "evidence-page"
    assert len(result) == 3
    assert len(memory.queries) <= 5
    assert all(len(query.split()) > 1 for query in memory.queries)
