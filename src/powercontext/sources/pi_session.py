"""Capture the visible history of one selected Pi session branch."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, JsonValue

from powercontext.sources.connectors import ConnectorRunCompletion, ConnectorRunSession, ConnectorRunStatus
from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence


class PiSessionInput(BaseModel):
    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


class PiEventSource(Source):
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


def _body(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for block in value:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "toolCall":
            name = block.get("name", "")
            call_id = block.get("id", "")
            arguments = json.dumps(
                block.get("arguments", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            parts.append(f"[tool_call {name} {call_id}] {arguments}")
    return "\n".join(parts)


def _visible(record: dict[str, JsonValue]) -> tuple[str, str] | None:
    kind = record.get("type")
    if kind == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        if not isinstance(role, str):
            return None
        if role == "bashExecution":
            command, output = message.get("command"), message.get("output")
            body = f"$ {command}\n{output}" if isinstance(command, str) and isinstance(output, str) else ""
        elif role == "toolResult":
            body = _body(message.get("content"))
            if body:
                body = f"[tool_result {message.get('toolName', '')} {message.get('toolCallId', '')}] {body}"
        else:
            body = _body(message.get("content"))
    elif kind in {"compaction", "branch_summary"}:
        role, body = str(kind), record.get("summary")
    elif kind == "custom_message":
        role, body = "custom", _body(record.get("content"))
    else:
        return None
    if not isinstance(body, str) or not body:
        return None
    return role, f"{role}: {body}"


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:  # noqa: C901
    try:
        records = [json.loads(line) for line in value.content.decode("utf-8-sig").splitlines() if line.strip()]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Pi JSONL") from exc  # noqa: TRY003
    if not records or not isinstance(records[0], dict):
        raise ValueError("missing Pi session header")  # noqa: TRY003
    header = records[0]
    session_id = header.get("id")
    if (
        header.get("type") != "session"
        or header.get("version") != 3
        or not isinstance(session_id, str)
        or not session_id
    ):
        raise ValueError("invalid Pi session header")  # noqa: TRY003
    nodes: dict[str, tuple[str | None, dict[str, JsonValue]]] = {}
    for record in records[1:]:
        if not isinstance(record, dict):
            raise ValueError("invalid Pi session node")  # noqa: TRY003, TRY004
        node_id, parent_id = record.get("id"), record.get("parentId")
        if not isinstance(node_id, str) or not node_id or node_id in nodes:
            raise ValueError("invalid Pi session graph")  # noqa: TRY003
        if parent_id is not None and (not isinstance(parent_id, str) or parent_id not in nodes):
            raise ValueError("invalid Pi session graph")  # noqa: TRY003
        nodes[node_id] = (parent_id, record)
    leaf = value.leaf_id if value.leaf_id is not None else next(reversed(nodes), None)
    if leaf is None:
        return ()
    if leaf not in nodes:
        raise ValueError("Pi leaf not found")  # noqa: TRY003
    path: list[tuple[str, str | None, dict[str, JsonValue]]] = []
    visited: set[str] = set()
    while leaf is not None:
        if leaf in visited:
            raise ValueError("cyclic Pi session")  # noqa: TRY003
        visited.add(leaf)
        parent_id, record = nodes[leaf]
        path.append((leaf, parent_id, record))
        leaf = parent_id
    events: list[PiEventInput] = []
    for event_id, parent_id, record in reversed(path):
        visible = _visible(record)
        if visible is not None:
            role, content = visible
            event_type = record.get("type")
            events.append(
                PiEventInput(
                    session_id=session_id,
                    event_id=event_id,
                    parent_id=parent_id,
                    event_type=event_type if isinstance(event_type, str) else "",
                    role=role,
                    content=content,
                    record=record,
                )
            )
    return tuple(events)


def _identity(session_id: str, event_id: str) -> str:
    encoded = json.dumps([session_id, event_id], ensure_ascii=False, separators=(",", ":")).encode()
    return "pi:" + hashlib.sha256(encoded).hexdigest()


class PiEventSourceAdapter:
    input_class = PiEventInput
    name = "pi-event"
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        return PiEventSource(
            name=_identity(value.session_id, value.event_id),
            materialization=SourceMaterialization.CAPTURED,
            **value.model_dump(),
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput.model_validate(
            source.model_dump(exclude={"name", "definition_version", "materialization", "description"})
        )


class PiEventTextEvidenceProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type="pi-event",
            source_id=source.name,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition(
    PiEventSourceAdapter(), projections=(PiEventTextEvidenceProjection(),)
)


class PiSessionConnector:
    name = "pi-session-history"
    version = "1"
    source_definitions = frozenset({"pi-event"})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self.path = Path(path)
        self.leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        events = parse_pi_session(PiSessionInput(content=self.path.read_bytes(), leaf_id=self.leaf_id))
        previous = session.checkpoint
        if previous is None:
            seen: dict[str, str] = {}
        elif isinstance(previous, dict) and isinstance(previous.get("seen"), dict):
            seen = dict(previous["seen"])
        else:
            raise ValueError("invalid Pi checkpoint")  # noqa: TRY003
        for event in events:
            identity = _identity(event.session_id, event.event_id)
            digest = hashlib.sha256(
                json.dumps(event.record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if identity in seen:
                if seen[identity] != digest:
                    raise ValueError("previously captured Pi event changed")  # noqa: TRY003
                continue
            await session.submit(identity, "pi-event", event)
            seen[identity] = digest
        return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint={"seen": seen})
