"""Document selection uses runtime IDs and preserves ambiguous queries."""

import asyncio
from types import SimpleNamespace

from powercontext.artifacts.models import ArtifactRef, MemoryCitation
from powercontext.sources.pdf_pages import search_pdf_pages


def test_mixed_pdf_collection_scopes_only_a_named_document() -> None:
    memory_ref = ArtifactRef(family="memory", artifact_id="mixed-pdfs", revision=1)

    def record(document: str, number: int) -> SimpleNamespace:
        entry_id = f"{document}-{number}"
        citation = MemoryCitation(memory_ref=memory_ref, entry_id=entry_id, entry_version_id=f"v-{entry_id}")
        return SimpleNamespace(
            entry=SimpleNamespace(
                text=f"{document}\nOperating cash flow and sales in the annual report.",
                entry_id=entry_id,
                entry_version_id=citation.entry_version_id,
            ),
            citation=citation,
        )

    entries = (
        *(record("Boreal_2022_10K", number) for number in range(30)),
        record("Atlas_2022_10K", 1),
    )

    class Memory:
        async def search(self, request):
            return SimpleNamespace(hits=())

        async def list(self):
            return SimpleNamespace(entries=entries)

    selected = asyncio.run(search_pdf_pages(Memory(), "What was Atlas operating cash flow?", limit=20))
    assert [citation.entry_id for citation in selected] == ["Atlas_2022_10K-1"]

    unscoped = asyncio.run(search_pdf_pages(Memory(), "What was operating cash flow?", limit=31))
    assert len(unscoped) == 31


def test_financial_metric_routes_to_statement_without_word_overlap() -> None:
    memory_ref = ArtifactRef(family="memory", artifact_id="statements", revision=1)

    def record(number: int, text: str) -> SimpleNamespace:
        citation = MemoryCitation(memory_ref=memory_ref, entry_id=f"page-{number}", entry_version_id=f"v-{number}")
        return SimpleNamespace(
            entry=SimpleNamespace(
                text=f"report_2022_10k\n{text}", entry_id=citation.entry_id, entry_version_id=citation.entry_version_id
            ),
            citation=citation,
        )

    entries = (
        *(record(number, "Annual report ratio overview") for number in range(30)),
        record(30, "Consolidated Balance Sheets\nCash and receivables. Current liabilities."),
    )

    class Memory:
        async def search(self, request):
            return SimpleNamespace(hits=())

        async def list(self):
            return SimpleNamespace(entries=entries)

    result = asyncio.run(search_pdf_pages(Memory(), "What was the quick ratio?", limit=5))
    assert result[0].entry_id == "page-30"


def test_operations_heading_is_an_income_statement_anchor() -> None:
    memory_ref = ArtifactRef(family="memory", artifact_id="operations", revision=1)

    def record(number: int, text: str) -> SimpleNamespace:
        citation = MemoryCitation(memory_ref=memory_ref, entry_id=f"page-{number}", entry_version_id=f"v-{number}")
        return SimpleNamespace(
            entry=SimpleNamespace(
                text=f"report_2022_10k\n{text}", entry_id=citation.entry_id, entry_version_id=citation.entry_version_id
            ),
            citation=citation,
        )

    entries = (
        *(
            record(number, "The operating margin discussion includes details of business segments.")
            for number in range(30)
        ),
        record(30, "Consolidated Statements of Operations\nNet revenue and cost of sales."),
    )

    class Memory:
        async def search(self, request):
            return SimpleNamespace(hits=())

        async def list(self):
            return SimpleNamespace(entries=entries)

    result = asyncio.run(search_pdf_pages(Memory(), "Calculate the operating margin from the report", limit=5))
    assert result[0].entry_id == "page-30"


def test_multiple_financial_statement_pages_survive_distractors() -> None:
    memory_ref = ArtifactRef(family="memory", artifact_id="multi-page", revision=1)

    def record(number: int, text: str) -> SimpleNamespace:
        citation = MemoryCitation(memory_ref=memory_ref, entry_id=f"page-{number}", entry_version_id=f"v-{number}")
        return SimpleNamespace(
            entry=SimpleNamespace(
                text=f"report_2022_10k\n{text}", entry_id=citation.entry_id, entry_version_id=citation.entry_version_id
            ),
            citation=citation,
        )

    entries = (
        *(record(number, "Operating margin discussed in the business overview.") for number in range(30)),
        record(30, "Consolidated Statements of Operations\nRevenue 2022 100 2021 90\nCost 2022 60 2021 55"),
        record(31, "Consolidated Statements of Operations\nIncome 2022 40 2021 35\nTax 2022 10 2021 8"),
    )

    class Memory:
        async def search(self, request):
            return SimpleNamespace(hits=())

        async def list(self):
            return SimpleNamespace(entries=entries)

    result = asyncio.run(search_pdf_pages(Memory(), "What was the operating margin?", limit=5))
    assert {"page-30", "page-31"} <= {citation.entry_id for citation in result}
