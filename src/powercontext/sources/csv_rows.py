"""Captured CSV records with stable row identity and text evidence."""

from __future__ import annotations

import csv
import io
import json
from urllib.parse import quote

from pydantic import BaseModel

from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence


class CSVDocumentInput(BaseModel):
    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    if not document_id or document_id != document_id.strip():
        raise ValueError("document_id must be non-empty and have no surrounding whitespace")  # noqa: TRY003
    if not primary_key_value or not primary_key_value.strip():
        raise ValueError("primary_key_value must be non-blank")  # noqa: TRY003
    source_id = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(source_id) > 256:
        raise ValueError("CSV row source ID exceeds 256 characters")  # noqa: TRY003
    return source_id


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    if not value.document_id or value.document_id != value.document_id.strip():
        raise ValueError("document_id must be non-empty and have no surrounding whitespace")  # noqa: TRY003
    if not value.primary_key:
        raise ValueError("primary_key must be non-empty")  # noqa: TRY003
    try:
        text = value.content.decode("utf-8-sig", errors="strict")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        columns = tuple(next(reader))
        if not columns or any(not column.strip() for column in columns) or len(set(columns)) != len(columns):
            raise ValueError("CSV header must contain unique, non-blank columns")  # noqa: TRY003
        if value.primary_key not in columns:
            raise ValueError("primary_key must exactly match a column")  # noqa: TRY003
        key_index = columns.index(value.primary_key)
        rows: list[CSVRowInput] = []
        seen: set[str] = set()
        for record in reader:
            if not record:
                continue
            if len(record) != len(columns):
                raise ValueError("CSV row width differs from header")  # noqa: TRY003
            key = record[key_index]
            if not key.strip() or key in seen:
                raise ValueError("CSV row primary key is blank or duplicated")  # noqa: TRY003
            csv_row_source_id(value.document_id, key)
            seen.add(key)
            rows.append(
                CSVRowInput(
                    document_id=value.document_id,
                    primary_key=value.primary_key,
                    primary_key_value=key,
                    columns=columns,
                    values=tuple(record),
                )
            )
        return tuple(rows)
    except (UnicodeError, csv.Error, StopIteration) as exc:
        raise ValueError("invalid CSV document") from exc  # noqa: TRY003


class CSVRowSourceAdapter:
    input_class = CSVRowInput
    name = "csv-row"
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        if not value.columns or len(value.columns) != len(value.values):
            raise ValueError("CSV row has invalid column/value width")  # noqa: TRY003
        if value.primary_key not in value.columns:
            raise ValueError("primary_key must exactly match a column")  # noqa: TRY003
        if value.values[value.columns.index(value.primary_key)] != value.primary_key_value:
            raise ValueError("primary_key_value does not match the row")  # noqa: TRY003
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=source.columns,
            values=source.values,
        )


class CSVRowTextEvidenceProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(
            source_type="csv-row",
            source_id=source.source_id,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(
    CSVRowSourceAdapter(), projections=(CSVRowTextEvidenceProjection(),)
)
