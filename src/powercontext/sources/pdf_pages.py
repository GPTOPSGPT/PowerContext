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


async def search_pdf_pages(memory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    if limit <= 0:
        return ()
    # FTS is scoped by the caller's Memory handle. Try the full question and its
    # content words to recover pages whose text does not repeat the question verbatim.
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
    distinctive = [
        term
        for term in dict.fromkeys(terms)
        if len(term) > 3 and term not in stop and not (term.isdigit() and len(term) == 4)
    ]
    normalized_question = question.lower()
    finance_terms = []
    for pattern, expanded in (
        (r"\bcapex\b", ("capital", "expenditures")),
        (r"\bd\s*&\s*a\b", ("depreciation", "amortization")),
        (r"\bp\s*&\s*l\b", ("income", "statement")),
        (r"\bebitda\b", ("operating", "income", "depreciation", "amortization")),
    ):
        if re.search(pattern, normalized_question):
            finance_terms.extend(expanded)
    # A long natural-language query can miss a page that covers only one of its
    # concepts. Search a few short, overlapping concept groups as well. Unlike
    # single-word searches, these require at least two matching terms in Memory.
    starts = (0, len(distinctive) // 2, max(0, len(distinctive) - 5))
    queries = [question, *(" ".join(distinctive[start : start + 5]) for start in starts)]
    if finance_terms:
        queries.append(" ".join(dict.fromkeys(finance_terms)))
    candidates = {}
    for query in dict.fromkeys(query for query in queries if query.strip()):
        page = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=max(limit * 3, 60)))
        for rank, hit in enumerate(page.hits):
            key = (hit.entry_id, hit.entry_version_id)
            if key not in candidates:
                candidates[key] = (hit, 0.0)
            original, score = candidates[key]
            candidates[key] = (original, score + 1.0 / (60 + rank))

    if not candidates:
        return ()
    query_terms = set(distinctive) | set(finance_terms)
    page_terms = {key: set(re.findall(r"[a-z]+|\d+", hit.text.lower())) for key, (hit, _) in candidates.items()}
    document_frequency = Counter(term for terms_on_page in page_terms.values() for term in terms_on_page & query_terms)
    weights = {term: math.log((len(candidates) + 1) / (document_frequency[term] + 1)) + 1 for term in query_terms}
    total_weight = sum(weights.values()) or 1.0
    ranked = sorted(
        candidates,
        key=lambda key: (
            -sum(weights[term] for term in page_terms[key] & query_terms) / total_weight - candidates[key][1],
            key,
        ),
    )[:limit]
    return tuple(
        MemoryCitation(
            memory_ref=candidates[key][0].memory_ref,
            entry_id=candidates[key][0].entry_id,
            entry_version_id=candidates[key][0].entry_version_id,
        )
        for key in ranked
    )
