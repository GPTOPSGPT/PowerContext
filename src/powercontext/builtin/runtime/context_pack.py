# ruff: noqa: TRY003
"""Versioned, independently decodable full and incremental context payloads."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast

_PACK_SCHEMA = "powercontext.context-pack.v1"
_DELTA_SCHEMA = "powercontext.context-pack-delta.v1"


class ContextPackError(ValueError):
    """A context pack or delta violates the wire protocol."""


def _wire(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: dict[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_wire(value)).hexdigest()


def _encode(items: tuple[bytes, ...]) -> list[str]:
    return [base64.b64encode(item).decode("ascii") for item in items]


def _decode(values: object) -> tuple[bytes, ...]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ContextPackError("items must be a list of Base64 strings")
    encoded = cast(list[str], values)
    try:
        decoded = tuple(base64.b64decode(value, validate=True) for value in encoded)
    except (binascii.Error, ValueError) as exc:
        raise ContextPackError("invalid Base64 item") from exc
    if _encode(decoded) != encoded:
        raise ContextPackError("noncanonical Base64 item")
    return decoded


def _read_wire(data: bytes, fields: set[str]) -> dict[str, Any]:
    try:
        pairs = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ContextPackError("invalid JSON payload") from exc
    if not isinstance(pairs, dict) or set(pairs) != fields:
        raise ContextPackError("incomplete or unexpected payload")
    return pairs


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContextPackError("duplicate JSON field")
        result[key] = value
    return result


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


@dataclass(frozen=True, slots=True)
class ContextPack:
    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: tuple[bytes, ...]) -> ContextPack:
        if not isinstance(items, tuple) or any(not isinstance(item, bytes) for item in items):
            raise ContextPackError("items must be a tuple of bytes")
        digest = _digest({"schema": _PACK_SCHEMA, "items": _encode(items)})
        count = 0
        while True:
            payload = _wire({"schema": _PACK_SCHEMA, "items": _encode(items), "digest": digest, "byte_count": count})
            if len(payload) == count:
                return cls(items, digest, count)
            count = len(payload)

    @classmethod
    def from_content(cls, content: str, *, chunk_bytes: int = 512) -> ContextPack:
        if not isinstance(content, str) or type(chunk_bytes) is not int or chunk_bytes < 1:
            raise ContextPackError("invalid content or chunk size")
        chunks: list[bytes] = []
        current = bytearray()
        for character in content:
            encoded = character.encode("utf-8")
            if len(encoded) > chunk_bytes:
                raise ContextPackError("a UTF-8 character exceeds the chunk limit")
            if len(current) + len(encoded) > chunk_bytes:
                chunks.append(bytes(current))
                current.clear()
            current.extend(encoded)
        if current:
            chunks.append(bytes(current))
        return cls.build(tuple(chunks))

    def to_bytes(self) -> bytes:
        return _wire({
            "schema": _PACK_SCHEMA,
            "items": _encode(self.items),
            "digest": self.digest,
            "byte_count": self.byte_count,
        })

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPack:
        payload = _read_wire(data, {"schema", "items", "digest", "byte_count"})
        if payload["schema"] != _PACK_SCHEMA or type(payload["byte_count"]) is not int:
            raise ContextPackError("invalid pack schema or byte count")
        items = _decode(payload["items"])
        expected = cls.build(items)
        if payload["digest"] != expected.digest or payload["byte_count"] != expected.byte_count:
            raise ContextPackError("pack digest or byte count mismatch")
        return expected


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        _validated_pack(base)
        _validated_pack(target)
        prefix = 0
        for left, right in zip(base.items, target.items, strict=False):
            if left != right:
                break
            prefix += 1
        return cls(base.digest, target.digest, prefix, target.items[prefix:])

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    def to_bytes(self) -> bytes:
        return _wire({
            "schema": _DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": _encode(self.appended),
        })

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPackDelta:
        payload = _read_wire(data, {"schema", "base_digest", "target_digest", "prefix_items", "appended"})
        if (
            payload["schema"] != _DELTA_SCHEMA
            or not _valid_digest(payload["base_digest"])
            or not _valid_digest(payload["target_digest"])
            or type(payload["prefix_items"]) is not int
            or payload["prefix_items"] < 0
        ):
            raise ContextPackError("invalid delta fields")
        return cls(
            payload["base_digest"], payload["target_digest"], payload["prefix_items"], _decode(payload["appended"])
        )


def _validated_pack(pack: ContextPack) -> None:
    if ContextPack.build(pack.items) != pack:
        raise ContextPackError("invalid context pack")


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    _validated_pack(base)
    if (
        not _valid_digest(delta.base_digest)
        or not _valid_digest(delta.target_digest)
        or delta.base_digest != base.digest
        or type(delta.prefix_items) is not int
        or delta.prefix_items < 0
        or delta.prefix_items > len(base.items)
    ):
        raise ContextPackError("invalid delta base or prefix")
    target = ContextPack.build(base.items[: delta.prefix_items] + delta.appended)
    if target.digest != delta.target_digest:
        raise ContextPackError("delta target digest mismatch")
    return target
