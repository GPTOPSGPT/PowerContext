# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Persistent evidence dependency and availability for Source-derived content."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator
from sqlalchemy import insert, select, update

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_NODES_TABLE
from powercontext.sources import SourceRef

if TYPE_CHECKING:
    from powercontext.builtin.persistence.database import AsyncDatabase
    from powercontext.builtin.runtime.application import BuiltinRuntime


class SourceLifecycleError(ValueError):
    """A lifecycle registration, transition, or generation read is invalid."""


class SourceLifecycleEvent(BaseModel):
    """One ordered availability change for a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    revision: StrictInt
    sequence: StrictInt
    available: StrictBool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be nonblank")
        return value

    @field_validator("revision", "sequence")
    @classmethod
    def positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be positive")
        return value


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(value: bytes) -> object:
    return json.loads(value)


class SourceLifecycleApplication:
    """Select a persistent lifecycle service for one scope."""

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase) -> None:
        self._runtime = runtime
        self._database = database

    def for_scope(self, scope_id: str) -> ScopedSourceLifecycle:
        return ScopedSourceLifecycle(self._runtime, self._database, scope_id)


class ScopedSourceLifecycle:
    """Register a DAG and propagate Source withdrawal to native read models."""

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase, scope_id: str) -> None:
        self._runtime = runtime
        self._database = database
        self.scope_id = scope_id

    async def _nodes(self) -> dict[str, dict]:
        async with self._database.transaction() as connection:
            rows = (await connection.execute(
                select(SOURCE_LIFECYCLE_NODES_TABLE).where(SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id)
            )).mappings()
            return {str(row["node_id"]): dict(row) for row in rows}

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int) -> None:
        if type(revision) is not int or revision < 1:
            raise SourceLifecycleError("source revision must be positive")
        await self._runtime.records.for_scope(self.scope_id).get_source(source_ref.source_type, source_ref.source_id)
        await self._register(node_id, "source", source_ref.model_dump(mode="json"), (), None, True, revision)

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        await self._runtime.memory.for_scope(self.scope_id).get(
            self._memory_get_request(citation)
        )
        await self._register(node_id, "memory", citation.model_dump(mode="json"), parents, policy, False, None)

    async def register_topic(
        self,
        node_id: str,
        artifact_ref: ArtifactRef,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
            "topic-memory", artifact_ref.artifact_id, artifact_ref.revision
        )
        await self._register(node_id, "topic", artifact_ref.model_dump(mode="json"), parents, policy, False, None)

    @staticmethod
    def _memory_get_request(citation: MemoryCitation):
        from powercontext.builtin.runtime.application import GetMemoryEntryRequest
        return GetMemoryEntryRequest(citation=citation)

    async def _register(
        self, node_id: str, kind: str, reference: dict, parents: tuple[str, ...],
        policy: str | None, source_available: bool, revision: int | None,
    ) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError("node_id must be nonblank")
        if kind != "source" and (policy not in {"all", "any"} or not parents):
            raise SourceLifecycleError("derived nodes require parents and an all/any policy")
        if len(parents) != len(set(parents)) or node_id in parents:
            raise SourceLifecycleError("duplicate or cyclic parent")
        nodes = await self._nodes()
        expected = (kind, _encode(reference), _encode(parents), policy, revision)
        current = nodes.get(node_id)
        if current is not None:
            actual = (current["kind"], current["reference"], current["parents"], current["policy"], current["revision"])
            if actual != expected:
                raise SourceLifecycleError("node_id already has a different binding")
            return
        if any(parent not in nodes for parent in parents):
            raise SourceLifecycleError("parent is not registered")
        available = source_available if kind == "source" else self._supported(policy, parents, {
            key: bool(row["available"]) for key, row in nodes.items()
        })
        if kind == "memory" and not available:
            await self._set_memory_state(MemoryCitation.model_validate(reference), available)
        artifact_id = reference.get("artifact_id") if kind == "topic" else None
        artifact_revision = reference.get("revision") if kind == "topic" else None
        async with self._database.transaction() as connection:
            await connection.execute(insert(SOURCE_LIFECYCLE_NODES_TABLE).values(
                scope_id=self.scope_id, node_id=node_id, kind=kind, reference=_encode(reference),
                parents=_encode(parents), policy=policy, available=available, revision=revision,
                sequence=0, artifact_id=artifact_id, artifact_revision=artifact_revision,
            ))

    @staticmethod
    def _supported(policy: str | None, parents: tuple[str, ...], states: dict[str, bool]) -> bool:
        support = [states[parent] for parent in parents]
        return all(support) if policy == "all" else any(support)

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:
        nodes = await self._nodes()
        source = nodes.get(event.node_id)
        if source is None or source["kind"] != "source" or source["revision"] != event.revision:
            raise SourceLifecycleError("unknown Source or lifecycle revision")
        previous = source["sequence"]
        encoded_event = _encode(event.model_dump(mode="json"))
        if event.sequence < previous or (event.sequence == previous and source["last_event"] != encoded_event):
            raise SourceLifecycleError("Source event sequence conflicts")
        if event.sequence == previous:
            return sorted(key for key, row in nodes.items() if row["available"])
        states: dict[str, bool] = {event.node_id: event.available}
        def active(node_id: str) -> bool:
            if node_id in states:
                return states[node_id]
            row = nodes[node_id]
            if row["kind"] == "source":
                states[node_id] = bool(row["available"])
            else:
                parents = tuple(_decode(row["parents"]))
                states[node_id] = self._supported(row["policy"], parents, {parent: active(parent) for parent in parents})
            return states[node_id]
        for node_id in nodes:
            active(node_id)
        for node_id, row in nodes.items():
            if row["kind"] == "memory" and states[node_id] != bool(row["available"]):
                await self._set_memory_state(MemoryCitation.model_validate(_decode(row["reference"])), states[node_id])
        async with self._database.transaction() as connection:
            table = SOURCE_LIFECYCLE_NODES_TABLE
            for node_id, available in states.items():
                await connection.execute(update(table).where(
                    table.c.scope_id == self.scope_id, table.c.node_id == node_id
                ).values(available=available))
            await connection.execute(update(table).where(
                table.c.scope_id == self.scope_id, table.c.node_id == event.node_id
            ).values(sequence=event.sequence, last_event=encoded_event))
        return sorted(node_id for node_id, available in states.items() if available)

    async def _set_memory_state(self, citation: MemoryCitation, available: bool) -> None:
        async with self._runtime._context(self.scope_id) as context, self._runtime._locked(self.scope_id):
            service = context.artifacts.memory
            current = await service.head(context.artifacts.memory_artifact_id)
            manifest = next((item for item in current.content.manifest.entries if item.entry_id == citation.entry_id), None)
            if manifest is None or manifest.entry_version_id != citation.entry_version_id:
                raise SourceLifecycleError("registered Memory entry is no longer current")
            if (manifest.state == "active") == available:
                return
            entry = next(item for item in await service.entries(current) if item.entry_id == citation.entry_id)
            if available:
                await service.reactivate(current, entries=(entry,), reason="source lifecycle restored")
            else:
                await service.forget(current, entries=(entry,), reason="source lifecycle withdrawn")

    async def resolve(self, node_id: str, *, purpose: Literal["generation", "audit"]):
        if purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("unknown resolution purpose")
        row = (await self._nodes()).get(node_id)
        if row is None or (purpose == "generation" and not row["available"]):
            raise SourceLifecycleError("node is unavailable")
        payload = _decode(row["reference"])
        return {"source": SourceRef, "memory": MemoryCitation, "topic": ArtifactRef}[row["kind"]].model_validate(payload)


__all__ = ["SourceLifecycleApplication", "SourceLifecycleError", "SourceLifecycleEvent"]
