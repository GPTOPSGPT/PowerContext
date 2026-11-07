"""Focused contract checks for source refresh and persisted task context."""
import os
import unittest
from unittest.mock import patch

from sdd_context import context


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql):
        self.sql = sql

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows):
        self.cur = Cursor(rows)

    def cursor(self, *_):
        return self.cur


class ContextTests(unittest.TestCase):
    def test_db_sources_and_saved_progress_are_used_in_assistant_input(self):
        rows = [
            {"path": "sample/spec.md", "kind": "spec", "sha256": "new", "content": "Negative quantity raises ValueError"},
            {"path": "sample/pricing.py", "kind": "code", "sha256": "c", "content": "def invoice_total(...): ..."},
            {"path": "sample/test_pricing.py", "kind": "test", "sha256": "t", "content": "test_negative_quantity_rejected"},
        ]
        conn = Connection(rows)
        with patch.dict(os.environ, {"POWERCONTEXT_SCOPE_ID": "sdd-test"}), \
             patch("sdd_context.pc", return_value={"hits": [{"text": "Target test failed before fix"}]}):
            result = context(conn, "reject negative quantity")
        self.assertIn("FROM sdd_sources", conn.cur.sql)
        for row in rows:
            self.assertIn(row["path"], result["assistant_context"])
            self.assertIn(row["content"], result["assistant_context"])
        self.assertIn("Target test failed before fix", result["assistant_context"])
        rows[0] = {**rows[0], "sha256": "newer", "content": "Revised requirement"}
        with patch.dict(os.environ, {"POWERCONTEXT_SCOPE_ID": "sdd-test"}), \
             patch("sdd_context.pc", return_value={"hits": []}):
            refreshed = context(conn, "reject negative quantity")
        self.assertIn("Revised requirement", refreshed["assistant_context"])
        self.assertNotIn("Negative quantity raises ValueError", refreshed["assistant_context"])


if __name__ == "__main__":
    unittest.main()
