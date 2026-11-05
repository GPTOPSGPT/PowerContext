"""Capture every physical PDF page as independently citable text evidence."""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pypdf import PdfReader

from powercontext.artifacts.models import MemoryCitation
from powercontext.builtin.runtime import SearchMemoryRequest
from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

if TYPE_CHECKING:
    pass


class PDFDocumentInput(BaseModel):
    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    document_id: str
    document_sha256: str
    page_number: int
    text: str


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    if not value.document_id or not value.document_id.strip() or not value.content.startswith(b"%PDF-"):
        raise ValueError("invalid PDF input")  # noqa: TRY003
    digest = hashlib.sha256(value.content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(value.content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF requires a password")  # noqa: TRY003, TRY301
        pages = tuple(
            PDFPageInput(
                document_id=value.document_id,
                document_sha256=digest,
                page_number=number,
                text=page.extract_text() or "",
            )
            for number, page in enumerate(reader.pages, start=1)
        )
    except Exception as exc:
        raise ValueError("PDF could not be fully parsed") from exc  # noqa: TRY003
    if not pages:
        raise ValueError("PDF contains no pages")  # noqa: TRY003
    return pages


def _identity(value: PDFPageInput) -> str:
    document = value.document_id.encode("utf-8")
    document_key = hashlib.sha256(document).hexdigest()
    return f"pdf:{document_key}:{value.document_sha256}:{value.page_number}"


class PDFPageSourceAdapter:
    input_class = PDFPageInput
    name = "pdf-page"
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        return PDFPageSource(
            name=_identity(value),
            materialization=SourceMaterialization.CAPTURED,
            **value.model_dump(),
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type="pdf-page",
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDFPageSourceAdapter(), projections=(PDFPageTextEvidenceProjection(),)
)


def _section_anchors(entries, question: str, limit: int, score) -> list[int]:
    requested_sections = []
    if re.search(r"\b(?:income statements?|statements? of income|p\s*&\s*l)\b", question):
        requested_sections.append((r"\b(?:consolidated\s+)?statements? of income\b", 240))
    if re.search(r"\b(?:cash flows?|statements? of cash flows?)\b", question):
        requested_sections.append((r"\b(?:consolidated\s+)?statements? of cash flows?\b", 240))
    if re.search(r"\b(?:legal (?:battles?|proceedings?|disputes?|matters?)|litigation|lawsuits?)\b", question):
        requested_sections.append((r"\blegal proceedings\b", None))
    anchors = []
    for heading, window in requested_sections[:limit]:
        matching = [
            index for index, record in enumerate(entries) if re.search(heading, record.entry.text[:window].lower())
        ]
        if matching:
            anchors.append(max(matching, key=score))
    return anchors


async def search_pdf_pages(memory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    if limit <= 0:
        return ()
    # The scoped Memory's public list API contains the complete, citable page
    # collection. Rank that collection so FTS admission cannot discard an
    # evidence page that uses different wording from a long question.
    terms = re.findall(r"[a-z]+|\d+", question.lower())
    stop = {
        "what",
        "which",
        "where",
        "when",
        "who",
        "how",
        "does",
        "the",
        "and",
        "for",
        "from",
        "with",
        "that",
        "this",
        "are",
        "was",
        "were",
        "have",
        "has",
        "into",
        "than",
        "then",
        "about",
        "their",
        "using",
        "give",
        "answer",
        "question",
        "fy2022",
        "fy2021",
    }
    distinctive = [term for term in dict.fromkeys(terms) if len(term) > 3 and term not in stop and not term.isdigit()]
    aliases = {
        "capex": ("capital", "expenditures"),
        "ebitda": ("operating", "income", "depreciation", "amortization"),
        "geographies": ("geographic", "segments", "regions"),
        "restructuring": ("restructuring", "charges"),
    }
    query_terms = list(dict.fromkeys(term for word in distinctive for term in (word, *aliases.get(word, ()))))
    normalized = question.lower()
    if re.search(r"\bd\s*&\s*a\b", normalized):
        query_terms.extend(("depreciation", "amortization"))
    if re.search(r"\bp\s*&\s*l\b", normalized):
        query_terms.extend(("income", "statement"))
    query_terms = list(dict.fromkeys(query_terms))

    # Use search as a lexical channel, then rank every persisted page using
    # the public Memory API. Entries returned by list carry exact citations.
    searched = await memory.search(SearchMemoryRequest(query=question, mode="fts", limit=max(limit, 40)))
    lexical = {(hit.entry_id, hit.entry_version_id): rank for rank, hit in enumerate(searched.hits)}
    listed = await memory.list()
    entries = [record for record in listed.entries if record.entry.text.strip()]
    if not entries:
        return ()
    tokenized = [Counter(re.findall(r"[a-z]+|\d+", record.entry.text.lower())) for record in entries]
    frequency = Counter(term for counts in tokenized for term in query_terms if term in counts)
    total = len(entries)
    average_length = sum(sum(counts.values()) for counts in tokenized) / total

    def score(index: int) -> float:
        counts = tokenized[index]
        length = sum(counts.values())
        value = 0.0
        for term in query_terms:
            occurrences = counts[term]
            if occurrences:
                idf = math.log1p((total - frequency[term] + 0.5) / (frequency[term] + 0.5))
                value += idf * occurrences * 2.2 / (occurrences + 1.2 * (0.25 + 0.75 * length / average_length))
        identity = (entries[index].entry.entry_id, entries[index].entry.entry_version_id)
        if identity in lexical:
            value += 0.25 / (1 + lexical[identity])
        return value

    ranked = sorted(range(total), key=lambda index: (-score(index), index))
    # Long financial questions often name several statements. Keep a page
    # headed by each requested statement in the result, even when incidental
    # words in the question outweigh its title in a whole-page BM25 score.
    selected = list(dict.fromkeys(_section_anchors(entries, normalized, limit, score)))
    selected.extend(index for index in ranked if index not in selected)
    ranked = selected[:limit]
    return tuple(entries[index].citation for index in ranked)
