from __future__ import annotations

from types import SimpleNamespace

import pytest

from powercontext.builtin.artifacts.memory import (
    CapabilityNotSupportedError,
    EmbeddingProfile,
    Memory,
    MemoryCapabilities,
    MemoryContent,
    MemoryManifest,
    MemoryQueryEmbedding,
)
from powercontext.builtin.artifacts.memory.service import MemoryService
from powercontext.builtin.persistence.memory import RelationalMemoryBackend
from powercontext.builtin.persistence.memory_index import CompositeMemoryIndex
from powercontext.builtin.persistence.oceanbase.memory_index import OceanBaseMemoryVectorIndex

PROFILE = EmbeddingProfile(profile_id="test", model="test", dimension=3)
CAPABILITIES = MemoryCapabilities(fts=True, vector=True, hybrid=True, embedding_profile=PROFILE)


class _Backend:
    def __init__(self, *, validates_in_search: bool) -> None:
        self.validates_vector_complete_in_search = validates_in_search
        self.completeness_calls = 0

    async def vector_complete(self, _memories, _profile) -> bool:
        self.completeness_calls += 1
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "validates_in_search", "expected_calls"),
    [
        ("hybrid", True, 0),
        ("vector", True, 0),
        ("auto", True, 1),
        ("hybrid", False, 1),
    ],
)
async def test_explicit_search_defers_only_when_backend_validates(
    mode: str, validates_in_search: bool, expected_calls: int
) -> None:
    backend = _Backend(validates_in_search=validates_in_search)
    service = MemoryService(backend=backend, embedding_model=SimpleNamespace(profile=PROFILE))

    assert await service._select_search_mode(mode, memories=(), capabilities=CAPABILITIES) == (
        "hybrid" if mode == "auto" else mode
    )
    assert backend.completeness_calls == expected_calls


def test_only_exact_builtin_relational_index_has_deferred_validation() -> None:
    backend = RelationalMemoryBackend.__new__(RelationalMemoryBackend)
    backend._index = CompositeMemoryIndex(OceanBaseMemoryVectorIndex(PROFILE))
    assert backend.validates_vector_complete_in_search

    class _CustomRelationalBackend(RelationalMemoryBackend):
        pass

    custom = _CustomRelationalBackend.__new__(_CustomRelationalBackend)
    custom._index = backend._index
    assert not custom.validates_vector_complete_in_search

    backend._index = CompositeMemoryIndex(OceanBaseMemoryVectorIndex(PROFILE), OceanBaseMemoryVectorIndex(PROFILE))
    assert not backend.validates_vector_complete_in_search


@pytest.mark.asyncio
async def test_deferred_incomplete_hybrid_keeps_requested_error_category() -> None:
    memory = Memory(artifact_id="memory", revision=1, content=MemoryContent(manifest=MemoryManifest()))

    class _IncompleteBackend(_Backend):
        async def capabilities(self) -> MemoryCapabilities:
            return CAPABILITIES

        async def get(self, _ref) -> Memory:
            return memory

        async def latest(self, _artifact_id) -> Memory:
            return memory

        async def search(self, _request) -> None:
            raise CapabilityNotSupportedError("vector")

    backend = _IncompleteBackend(validates_in_search=True)
    service = MemoryService(backend=backend, embedding_model=SimpleNamespace(profile=PROFILE))
    with pytest.raises(CapabilityNotSupportedError) as raised:
        await service.search(
            "test",
            memories=(memory,),
            mode="hybrid",
            query_embedding=MemoryQueryEmbedding(query_vector=(1.0, 0.0, 0.0), embedding_profile=PROFILE),
        )
    assert raised.value.capability == "hybrid"
    assert backend.completeness_calls == 0
