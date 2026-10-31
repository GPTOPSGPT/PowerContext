"""Coalesce concurrent embedding requests and reuse successful vectors."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel


@dataclass(frozen=True, slots=True)
class _Resolved:
    vector: EmbeddingVector
    batch_id: int | None = None
    usage: InferenceUsage | None = None


class CoalescingEmbeddingModel:
    """Share in-flight work by exact text and cache completed vectors with LRU eviction."""

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if max_batch_size < 1 or coalesce_ms < 0 or cache_size < 0:
            raise ValueError("batch size must be positive; window and cache size must be nonnegative")  # noqa: TRY003
        self._model = model
        self.profile = model.profile
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = coalesce_ms / 1000
        self._cache_size = cache_size
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[_Resolved]] = {}
        self._pending: OrderedDict[str, asyncio.Future[_Resolved]] = OrderedDict()
        self._worker: asyncio.Task[None] | None = None
        self._next_batch_id = 0

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        items: dict[str, _Resolved | asyncio.Future[_Resolved]] = {}
        for text in texts:
            if text in items:
                continue
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                items[text] = _Resolved(cached)
                continue
            future = self._inflight.get(text)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight[text] = future
                self._pending[text] = future
            items[text] = future

        if self._pending and self._worker is None:
            self._worker = asyncio.create_task(self._drain())

        resolved: dict[str, _Resolved] = {}
        for text, item in items.items():
            resolved[text] = item if isinstance(item, _Resolved) else await asyncio.shield(item)

        billed = {item.batch_id: item.usage for item in resolved.values() if item.batch_id is not None}
        usages = tuple(usage for usage in billed.values() if usage is not None)
        return EmbeddingResult(
            vectors=tuple(resolved[text].vector for text in texts),
            usage=InferenceUsage(
                requests=sum(usage.requests for usage in usages),
                input_tokens=_sum_optional(usage.input_tokens for usage in usages),
                output_tokens=_sum_optional(usage.output_tokens for usage in usages),
            ),
        )

    async def _drain(self) -> None:
        try:
            await asyncio.sleep(self._coalesce_seconds)
            while self._pending:
                batch = tuple(
                    self._pending.popitem(last=False) for _ in range(min(self._max_batch_size, len(self._pending)))
                )
                texts = tuple(text for text, _ in batch)
                self._next_batch_id += 1
                batch_id = self._next_batch_id
                try:
                    result = await self._embed_batch(texts)
                except Exception as exc:
                    for text, future in batch:
                        self._inflight.pop(text, None)
                        if not future.done():
                            future.set_exception(exc)
                    continue
                for (text, future), vector in zip(batch, result.vectors, strict=True):
                    if self._cache_size:
                        self._cache[text] = vector
                        self._cache.move_to_end(text)
                        if len(self._cache) > self._cache_size:
                            self._cache.popitem(last=False)
                    self._inflight.pop(text, None)
                    if not future.done():
                        future.set_result(_Resolved(vector, batch_id, result.usage))
        finally:
            self._worker = None
            if self._pending:
                self._worker = asyncio.create_task(self._drain())

    async def _embed_batch(self, texts: tuple[str, ...]) -> EmbeddingResult:
        result = await self._model.embed(texts)
        if len(result.vectors) != len(texts):
            raise ValueError("embedding vector count does not match input count")  # noqa: TRY003
        return result


def _sum_optional(values: Iterable[int | None]) -> int | None:
    numbers = [value for value in values if value is not None]
    return sum(numbers) if numbers else None
