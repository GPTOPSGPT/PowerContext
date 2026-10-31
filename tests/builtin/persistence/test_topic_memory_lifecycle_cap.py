"""Withdrawn Topic candidates must not consume the fusion result budget."""

from __future__ import annotations

import asyncio

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.records import ArtifactWrite
from powercontext.builtin.runtime import (
    BuiltinConfig,
    CaptureSource,
    SearchTopicMemoryRequest,
    open_builtin_runtime,
)
from powercontext.builtin.runtime.source_lifecycle import SourceLifecycleEvent
from powercontext.builtin.scope import ScopeDraft


def test_active_topic_survives_more_withdrawn_candidates_than_fusion_cap() -> None:
    async def scenario() -> None:
        async with open_builtin_runtime(BuiltinConfig(database=SQLiteConfig())) as runtime:
            scope = await runtime.scopes.create(
                ScopeDraft(title="Topic cap", summary="Lifecycle search", idempotency_key="topic-cap")
            )
            sid = scope.scope_id
            lifecycle = runtime.lifecycle.for_scope(sid)
            for root in ("withdrawn", "active"):
                receipt = await runtime.sources.for_scope(sid).capture(
                    CaptureSource(source_id=root, content=root, metadata={})
                )
                await lifecycle.register_source(root, receipt.source_ref, revision=1)
            for number in range(21):
                active = number == 20
                node = f"topic-{number}"
                text = "needle" if active else "needle needle needle"
                created = await runtime.records.for_scope(sid).create_artifact(
                    "topic-memory",
                    ArtifactWrite(content={"title": text, "summary": text, "detail": text}),
                )
                ref = ArtifactRef(family="topic-memory", artifact_id=created.artifact_id, revision=created.revision)
                await lifecycle.register_topic(node, ref, parents=("active" if active else "withdrawn",), policy="all")
            await lifecycle.apply(
                SourceLifecycleEvent(node_id="withdrawn", revision=1, sequence=1, available=False, reason="withdrawal")
            )
            result = await runtime.topic_memory.for_scope(sid).search(SearchTopicMemoryRequest(query="needle", limit=1))
            assert len(result.hits) == 1
            assert result.hits[0].title == "needle"

    asyncio.run(scenario())
