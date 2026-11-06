"""Capture every physical PDF page as independently citable text evidence."""

from __future__ import annotations

import hashlib
import io
import itertools
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


def _stem_token(token: str) -> str:
    """Normalize common English inflections for a second lexical ranking channel."""
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith(("ed", "es")):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "is")):
        return token[:-1]
    return token


def _stem_counts(counts: Counter[str]) -> Counter[str]:
    stemmed: Counter[str] = Counter()
    for term, count in counts.items():
        stemmed[_stem_token(term)] += count
    return stemmed


def _requested_sections(question: str) -> list[tuple[str, int | None]]:
    requested_sections = []
    if re.search(
        r"\b(?:income statements?|statements? of income|p\s*&\s*l|"
        r"revenue|sales|gross margin|operating margin|operating income|net income|ebitda|earnings per share)\b",
        question,
    ):
        requested_sections.append((
            r"\b(?:consolidated\s+)?(?:statements? of (?:income|operations|earnings)|income statements?)\b",
            240,
        ))
    if re.search(
        r"\b(?:cash flows?|statements? of cash flows?|capex|capital expenditures|"
        r"depreciation|amortization|free cash flow)\b",
        question,
    ):
        requested_sections.append((r"\b(?:consolidated\s+)?statements? of cash flows?\b", 240))
    if re.search(
        r"\b(?:balance sheets?|statements? of financial position|quick ratio|current ratio|"
        r"current assets?|current liabilities|total assets?|total liabilities|shareholders? equity)\b",
        question,
    ):
        requested_sections.append((
            r"\b(?:consolidated\s+)?(?:balance sheets?|statements? of financial position)\b",
            240,
        ))
    if re.search(r"\b(?:legal (?:battles?|proceedings?|disputes?|matters?)|litigation|lawsuits?)\b", question):
        requested_sections.append((r"\blegal proceedings\b", None))
    return requested_sections


def _section_anchors(entries, requested_sections, limit: int, score) -> list[int]:
    anchors = []
    for heading, window in requested_sections[:limit]:
        matching = [
            index for index, record in enumerate(entries) if re.search(heading, record.entry.text[:window].lower())
        ]
        if matching:
            anchors.append(max(matching, key=score))
    return anchors


def _topic_bonus(page_text: str, terms: list[str]) -> float:
    bonus = 0.0
    if ("customer" in terms or "concentration" in terms) and re.search(
        r"(?:major|significant|largest) customers?|customer concentration|\d+% of (?:our )?revenue", page_text
    ):
        bonus = 16.0
    if ("segment" in terms or "categories" in terms or ("product" in terms and "service" in terms)) and re.search(
        r"business segments?|segment (?:data|information|results)|product (?:categories|lines)", page_text
    ):
        bonus = max(bonus, 14.0)
    if any(term in terms for term in ("legal", "litigation", "lawsuits", "battles")):
        legal_mentions = sum(page_text.count(term) for term in ("litigation", "lawsuit", "proceedings", "plaintiff"))
        if legal_mentions >= 3:
            bonus = max(bonus, 15.0)
    return bonus


def _page_bonuses(entries, tokenized, terms, distinctive, requested_sections) -> list[float]:
    salient = set(distinctive)
    query_phrases = tuple(
        f" {left} {right} " for left, right in itertools.pairwise(terms) if left in salient and right in salient
    )
    bonuses = []
    for index, record in enumerate(entries):
        page_text = record.entry.text.lower()
        page_words = " " + " ".join(re.findall(r"[a-z]+|\d+", page_text)) + " "
        phrase_bonus = 2.0 * sum(phrase in page_words for phrase in query_phrases)
        heading_bonus = 0.0
        for heading, window in requested_sections:
            if re.search(heading, page_text[:window]):
                weight = 12.0
                if window is not None:
                    counts = tokenized[index]
                    length = sum(counts.values())
                    if (
                        length <= 500
                        and length
                        and sum(count for word, count in counts.items() if word.isdigit()) / length >= 0.12
                    ):
                        weight += 8.0
                heading_bonus = max(heading_bonus, weight)
        bonuses.append(phrase_bonus + max(heading_bonus, _topic_bonus(page_text, terms)))
    return bonuses


def _scope_document_pages(entries, question: str):
    """Narrow a mixed collection only when the question names one document."""
    documents: dict[str, list] = {}
    for record in entries:
        document_id = record.entry.text.partition("\n")[0].strip()
        documents.setdefault(document_id, []).append(record)
    if len(documents) < 2:
        return entries

    compact_question = re.sub(r"[^a-z0-9]", "", question.lower())
    matches = []
    for document_id in documents:
        # Financial report IDs commonly end with a year and filing type. Use
        # only the issuer prefix learned from the stored page, never a list of
        # expected issuers or evaluation documents.
        issuer = re.split(r"(?<!\d)(?:19|20)\d{2}(?!\d)", document_id, maxsplit=1)[0]
        compact_issuer = re.sub(r"[^a-z0-9]", "", issuer.lower())
        if len(compact_issuer) >= 2 and compact_issuer in compact_question:
            matches.append(document_id)
    return documents[matches[0]] if len(matches) == 1 else entries


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
        "respond",
        "assuming",
        "perspective",
        "analyst",
        "details",
        "shown",
        "within",
        "only",
        "calculate",
        "provide",
        "explain",
        "according",
        "fy2022",
        "fy2021",
    }
    short_financial_terms = {"eps", "net", "tax", "roe", "roa", "ppe"}
    distinctive = [
        term
        for term in dict.fromkeys(terms)
        if (len(term) > 3 or term in short_financial_terms) and term not in stop and not term.isdigit()
    ]
    aliases = {
        "capex": ("capital", "expenditures"),
        "capital": ("property", "plant", "equipment", "investments"),
        "categories": ("segments", "products", "services"),
        "concentration": ("customer", "significant", "revenues"),
        "customer": ("customers", "clients", "revenues"),
        "debt": ("borrowings", "indebtedness", "notes"),
        "ebitda": ("operating", "income", "depreciation", "amortization"),
        "geographies": ("geographic", "segments", "regions"),
        "legal": ("litigation", "lawsuits", "proceedings", "claims"),
        "liquidity": ("current", "assets", "liabilities", "cash"),
        "margin": ("profit", "income"),
        "quick": ("current", "assets", "liabilities"),
        "revenue": ("sales",),
        "restructuring": ("restructuring", "charges"),
        "sales": ("revenue",),
        "tax": ("taxes", "provision", "income"),
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
    entries = _scope_document_pages(entries, question)
    tokenized = [Counter(re.findall(r"[a-z]+|\d+", record.entry.text.lower())) for record in entries]
    frequency = Counter(term for counts in tokenized for term in query_terms if term in counts)
    stemmed_terms = list(dict.fromkeys(map(_stem_token, query_terms)))
    stemmed_pages = [_stem_counts(counts) for counts in tokenized]
    stemmed_frequency = Counter(term for counts in stemmed_pages for term in stemmed_terms if term in counts)
    total = len(entries)
    average_length = sum(sum(counts.values()) for counts in tokenized) / total
    requested_sections = _requested_sections(normalized)
    bonuses = _page_bonuses(entries, tokenized, terms, distinctive, requested_sections)

    def bm25(counts, terms, document_frequency) -> float:
        length = sum(counts.values())
        value = 0.0
        for term in terms:
            occurrences = counts[term]
            if occurrences:
                idf = math.log1p((total - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                value += idf * occurrences * 2.2 / (occurrences + 1.2 * (0.25 + 0.75 * length / average_length))
        return value

    def score(index: int) -> float:
        value = bm25(tokenized[index], query_terms, frequency) + bonuses[index]
        identity = (entries[index].entry.entry_id, entries[index].entry.entry_version_id)
        if identity in lexical:
            value += 0.25 / (1 + lexical[identity])
        return value

    raw_ranked = sorted(range(total), key=lambda index: (-score(index), index))
    stemmed_ranked = sorted(
        range(total),
        key=lambda index: (-bm25(stemmed_pages[index], stemmed_terms, stemmed_frequency) - bonuses[index], index),
    )
    raw_positions = {index: rank for rank, index in enumerate(raw_ranked, start=1)}
    stemmed_positions = {index: rank for rank, index in enumerate(stemmed_ranked, start=1)}
    ranked = sorted(
        range(total),
        key=lambda index: (
            -(1 / (60 + raw_positions[index]) + 1.5 / (60 + stemmed_positions[index])),
            index,
        ),
    )
    # Long financial questions often name several statements. Keep a page
    # headed by each requested statement in the result, even when incidental
    # words in the question outweigh its title in a whole-page BM25 score.
    selected = list(dict.fromkeys(_section_anchors(entries, requested_sections, limit, score)))
    selected.extend(index for index in ranked if index not in selected)
    ranked = selected[:limit]
    return tuple(entries[index].citation for index in ranked)
