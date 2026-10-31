from __future__ import annotations

import asyncio

from powercontext.builtin.artifacts.memory import EmbeddingProfile
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel
from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage


def test_late_waiter_shares_inflight_even_with_cache_disabled() -> None:
    class Blocked:
        profile = EmbeddingProfile(profile_id="coalescing-test", model="offline", dimension=1)

        def __init__(self) -> None:
            self.calls = 0
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return EmbeddingResult(vectors=((float(len(texts[0])),),), usage=InferenceUsage(requests=1, input_tokens=3))

    async def scenario() -> None:
        base = Blocked()
        model = CoalescingEmbeddingModel(base, coalesce_ms=0, cache_size=0)
        first = asyncio.create_task(model.embed(("shared",)))
        await base.started.wait()
        second = asyncio.create_task(model.embed(("shared",)))
        await asyncio.sleep(0)
        base.release.set()
        one, two = await asyncio.gather(first, second)
        assert one.vectors == two.vectors == ((6.0,),)
        assert one.usage.input_tokens == two.usage.input_tokens == 3
        assert base.calls == 1
        await model.embed(("shared",))
        assert base.calls == 2

    asyncio.run(scenario())
