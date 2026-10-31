"""Pure query-guided selection of literal Memory evidence under an output-byte limit."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from powercontext.builtin.runtime.prepared_text import TRUST_POLICY

if TYPE_CHECKING:
    from powercontext.builtin.runtime.prepared_context import MemoryEntryAddress

_BEGIN = "BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1"
_END = "END_POWERCONTEXT_PREPARED_CONTEXT_V1"
_WORDS = re.compile(r"[a-z]+|\d+")
_SENTENCES = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")
_STOP = frozenset({
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "what",
    "which",
    "does",
    "have",
    "are",
    "was",
    "were",
    "how",
    "can",
    "into",
    "about",
    "their",
    "than",
})


@dataclass(frozen=True)
class EvidenceFragment:
    address: MemoryEntryAddress
    start: int
    end: int
    text: str


def _render(fragments: Sequence[EvidenceFragment]) -> str:
    items = [
        {
            "citation": {
                "scope_id": fragment.address.memory.scope_id,
                "memory_ref": fragment.address.memory.artifact.model_dump(mode="json"),
                "entry_id": fragment.address.entry_id,
                "entry_version_id": fragment.address.entry_version_id,
            },
            "content": fragment.text,
            "start": fragment.start,
            "end": fragment.end,
        }
        for fragment in fragments
    ]
    payload = json.dumps({"trust": "untrusted_history", "items": items}, ensure_ascii=False, separators=(",", ":"))
    return f"{TRUST_POLICY}\n\n{_BEGIN}\n{payload}\n{_END}"


def select_evidence(  # noqa: C901
    query: str,
    max_bytes: int,
    candidates: Sequence[tuple[MemoryEntryAddress, str]],
) -> tuple[str | None, tuple[EvidenceFragment, ...]]:
    query_terms = set(_WORDS.findall(query.lower())) - _STOP
    ranked: list[tuple[float, int, int, EvidenceFragment]] = []
    seen_entries: set[tuple[str, str, int, str, str]] = set()
    for rank, (address, text) in enumerate(candidates):
        key = (
            address.memory.scope_id,
            address.memory.artifact.artifact_id,
            address.memory.artifact.revision,
            address.entry_id,
            address.entry_version_id,
        )
        if key in seen_entries:
            continue
        seen_entries.add(key)
        for match in _SENTENCES.finditer(text):
            start, end = match.span()
            if not text[start:end].strip():
                continue
            terms = set(_WORDS.findall(text[start:end].lower()))
            overlap = query_terms & terms
            score = len(overlap) / max(1, len(query_terms)) + len(overlap) / max(1, len(terms))
            ranked.append((-score, rank, start, EvidenceFragment(address, start, end, text[start:end])))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    selected: list[EvidenceFragment] = []
    for _, _, _, fragment in ranked:
        proposed = (*selected, fragment)
        if len(_render(proposed).encode("utf-8")) <= max_bytes:
            selected.append(fragment)
            continue
        # A long sentence can still contribute an exact prefix within the budget.
        if selected:
            continue
        low, high = 1, len(fragment.text)
        while low <= high:
            middle = (low + high) // 2
            shorter = EvidenceFragment(
                fragment.address, fragment.start, fragment.start + middle, fragment.text[:middle]
            )
            if len(_render((shorter,)).encode("utf-8")) <= max_bytes:
                low = middle + 1
            else:
                high = middle - 1
        if high > 0:
            selected.append(
                EvidenceFragment(fragment.address, fragment.start, fragment.start + high, fragment.text[:high])
            )
    if not selected:
        return None, ()
    return _render(selected), tuple(selected)
