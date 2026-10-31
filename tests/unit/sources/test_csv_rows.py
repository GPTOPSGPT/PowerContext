from __future__ import annotations

import asyncio

import pytest

from powercontext.sources.csv_rows import (
    CSV_ROW_SOURCE_DEFINITION,
    CSVDocumentInput,
    CSVRowSource,
    csv_row_source_id,
    parse_csv_document,
)
from powercontext.sources.definitions import SourceDefinitionRegistry
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence


def test_csv_rows_preserve_columns_values_and_stable_identity() -> None:
    rows = parse_csv_document(
        CSVDocumentInput(
            document_id="airports/a.csv",
            primary_key=" id ",
            content='\ufeff id ,name,note\r\n 7 ,北京,"a,b"\r\n\r\n8,Paris,"x\ny"\r\n'.encode(),
        )
    )
    assert len(rows) == 2
    assert rows[0].columns == (" id ", "name", "note")
    assert rows[0].values == (" 7 ", "北京", "a,b")
    assert rows[1].values == ("8", "Paris", "x\ny")
    assert csv_row_source_id(rows[0].document_id, rows[0].primary_key_value) == "csv:airports%2Fa.csv:%207%20"


def test_definition_read_and_text_projection() -> None:
    row = parse_csv_document(CSVDocumentInput(document_id="doc", primary_key="id", content=b"id,name\n1,alice\n"))[0]
    registry = SourceDefinitionRegistry((CSV_ROW_SOURCE_DEFINITION,))
    source = asyncio.run(registry.resolve(row))
    assert isinstance(source, CSVRowSource)
    assert source.name == source.source_id == "csv:doc:1"
    assert asyncio.run(registry.read(source)) == row
    projected = TextEvidence.model_validate(registry.project(source, TEXT_EVIDENCE_PROJECTION_KEY))
    assert projected.content == '{"id":"1","name":"alice"}'
    assert projected.metadata["row"] == {"id": "1", "name": "alice"}


@pytest.mark.parametrize(
    "content",
    [b"", b"id,id\n1,2\n", b"id,name\n1\n", b"id,name\n1,a\n1,b\n", b"id,name\n,empty\n", b'id,name\n1,"broken'],
)
def test_invalid_csv_fails_atomically(content: bytes) -> None:
    with pytest.raises(ValueError):
        parse_csv_document(CSVDocumentInput(document_id="doc", primary_key="id", content=content))
