"""
Evidence Desk 自动化测试

运行方式:
    cd qoder && python -m pytest tests/ -v

需要设置环境变量指向 seekdb（或使用 .env 文件）。
如果数据库不可用，集成测试会被跳过，单元测试仍然执行。
"""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validation import validate_record, validate_search_params


# ── Validation Unit Tests ──────────────────────────────────────────────

class TestValidateRecord:
    def test_valid_record(self):
        data = {
            "title": "测试标题",
            "content": "测试正文内容",
            "source": "git:commit:abc123",
            "record_date": "2026-11-01",
            "tags": "测试,标签",
        }
        cleaned, err = validate_record(data)
        assert err is None
        assert cleaned["title"] == "测试标题"
        assert cleaned["record_date"] == date(2026, 11, 1)
        assert cleaned["tags"] == "测试,标签"

    def test_missing_title(self):
        data = {"title": "", "content": "内容", "source": "src", "record_date": "2026-11-01"}
        _, err = validate_record(data)
        assert "标题不能为空" in err

    def test_missing_content(self):
        data = {"title": "标题", "content": "", "source": "src", "record_date": "2026-11-01"}
        _, err = validate_record(data)
        assert "正文不能为空" in err

    def test_missing_source(self):
        data = {"title": "标题", "content": "内容", "source": "", "record_date": "2026-11-01"}
        _, err = validate_record(data)
        assert "来源不能为空" in err

    def test_invalid_date_format(self):
        data = {"title": "标题", "content": "内容", "source": "src", "record_date": "2026/11/01"}
        _, err = validate_record(data)
        assert "日期格式无效" in err

    def test_missing_date(self):
        data = {"title": "标题", "content": "内容", "source": "src", "record_date": ""}
        _, err = validate_record(data)
        assert "日期不能为空" in err

    def test_title_too_long(self):
        data = {"title": "x" * 501, "content": "内容", "source": "src", "record_date": "2026-11-01"}
        _, err = validate_record(data)
        assert "标题长度不能超过" in err

    def test_tags_optional(self):
        data = {"title": "标题", "content": "内容", "source": "src", "record_date": "2026-11-01", "tags": ""}
        cleaned, err = validate_record(data)
        assert err is None
        assert cleaned["tags"] == ""

    def test_whitespace_stripped(self):
        data = {"title": "  标题  ", "content": "  内容  ", "source": "  src  ", "record_date": "  2026-11-01  "}
        cleaned, err = validate_record(data)
        assert err is None
        assert cleaned["title"] == "标题"
        assert cleaned["content"] == "内容"
        assert cleaned["source"] == "src"


class TestValidateSearchParams:
    def test_empty_search(self):
        kw, d_from, d_to, err = validate_search_params("", "", "")
        assert err is None
        assert kw is None
        assert d_from is None
        assert d_to is None

    def test_keyword_only(self):
        kw, _, _, err = validate_search_params("认证", "", "")
        assert err is None
        assert kw == "认证"

    def test_date_range(self):
        _, d_from, d_to, err = validate_search_params("", "2026-10-01", "2026-10-31")
        assert err is None
        assert d_from == date(2026, 10, 1)
        assert d_to == date(2026, 10, 31)

    def test_invalid_date_from(self):
        _, _, _, err = validate_search_params("", "bad-date", "")
        assert "起始日期格式无效" in err

    def test_invalid_date_to(self):
        _, _, _, err = validate_search_params("", "", "bad-date")
        assert "结束日期格式无效" in err

    def test_date_from_after_to(self):
        _, _, _, err = validate_search_params("", "2026-11-01", "2026-10-01")
        assert "起始日期不能晚于结束日期" in err

    def test_keyword_too_long(self):
        _, _, _, err = validate_search_params("x" * 201, "", "")
        assert "关键词长度不能超过" in err


# ── Flask App Tests (with mocked DB) ───────────────────────────────────

class MockCursor:
    def __init__(self, results=None):
        self.results = results or []
        self.executed_sql = None
        self.executed_params = None
        self.lastrowid = 1
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.executed_sql = sql
        self.executed_params = params

    def executemany(self, sql, params_list):
        self.executed_sql = sql
        self.rowcount = len(params_list)

    def fetchall(self):
        return self.results

    def fetchone(self):
        return self.results[0] if self.results else None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockConnection:
    def __init__(self, cursor_results=None):
        self._cursor = MockCursor(cursor_results)
        self.committed = False

    def cursor(self, cursor_class=None):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


@pytest.fixture
def app():
    """Create a test Flask app with mocked database."""
    mock_conn = MockConnection()
    with patch("app.get_connection", return_value=mock_conn):
        with patch("app._get_conn", return_value=mock_conn):
            from app import app as flask_app
            flask_app.config["TESTING"] = True
            yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestIndexRoute:
    def test_index_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Evidence Desk" in resp.data


class TestImportRoute:
    def test_import_get(self, client):
        resp = client.get("/import")
        assert resp.status_code == 200
        assert b"JSON" in resp.data

    def test_import_post_valid(self, client):
        data = json.dumps([{
            "title": "测试导入",
            "content": "导入测试内容",
            "source": "test:import",
            "record_date": "2026-11-01",
            "tags": "测试",
        }])
        resp = client.post("/import", data={"json_data": data}, follow_redirects=True)
        assert resp.status_code == 200
        assert b"\xe6\x88\x90\xe5\x8a\x9f\xe5\xaf\xbc\xe5\x85\xa5" in resp.data  # "成功导入"

    def test_import_post_empty(self, client):
        resp = client.post("/import", data={"json_data": ""})
        assert resp.status_code == 400

    def test_import_post_invalid_json(self, client):
        resp = client.post("/import", data={"json_data": "{invalid"})
        assert resp.status_code == 400

    def test_import_post_invalid_record(self, client):
        data = json.dumps([{"title": "", "content": "", "source": "", "record_date": ""}])
        resp = client.post("/import", data={"json_data": data}, follow_redirects=True)
        assert resp.status_code == 200


class TestSearchRoute:
    def test_search_no_params(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200

    def test_search_with_keyword(self, client):
        resp = client.get("/search?q=认证")
        assert resp.status_code == 200

    def test_search_with_dates(self, client):
        resp = client.get("/search?date_from=2026-10-01&date_to=2026-10-31")
        assert resp.status_code == 200

    def test_search_invalid_date(self, client):
        resp = client.get("/search?date_from=bad")
        assert resp.status_code == 200


class TestReportRoute:
    def test_report_no_ids(self, client):
        resp = client.get("/report")
        assert resp.status_code == 200
        assert b"\xe8\xaf\xb7\xe9\x80\x89\xe6\x8b\xa9" in resp.data  # "请选择"

    def test_report_with_ids(self, client):
        sample_records = [
            {"id": 1, "title": "测试记录", "content": "测试内容", "source": "test:src", "record_date": "2026-11-01", "tags": "测试"},
        ]
        mock_conn = MockConnection(sample_records)
        with patch("app._get_conn", return_value=mock_conn):
            resp = client.get("/report?ids=1")
            assert resp.status_code == 200
            assert b"\xe6\xb5\x8b\xe8\xaf\x95\xe8\xae\xb0\xe5\xbd\x95" in resp.data  # "测试记录"


class TestApiSearch:
    def test_api_search_empty(self, client):
        resp = client.get("/api/search")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "records" in data
        assert "count" in data

    def test_api_search_invalid_date(self, client):
        resp = client.get("/api/search?date_from=bad")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


# ── Draft Generation Unit Test ─────────────────────────────────────────

class TestDraftGeneration:
    def test_generate_draft_empty(self):
        from app import _generate_draft
        result = _generate_draft([])
        assert "请选择" in result

    def test_generate_draft_single(self):
        from app import _generate_draft
        records = [{
            "id": 1,
            "title": "完成用户认证模块重构",
            "content": "将原有的 session-based 认证迁移到 JWT token 方案。",
            "source": "git:commit:a3f8c21 / src/auth/jwt.py",
            "record_date": "2026-10-27",
            "tags": "后端,认证",
        }]
        draft = _generate_draft(records)
        assert "# 周报草稿" in draft
        assert "完成用户认证模块重构" in draft
        assert "git:commit:a3f8c21" in draft
        assert "#1" in draft

    def test_generate_draft_multiple_tags(self):
        from app import _generate_draft
        records = [
            {"id": 1, "title": "任务A", "content": "内容A", "source": "src:A", "record_date": "2026-11-01", "tags": "后端,API"},
            {"id": 2, "title": "任务B", "content": "内容B", "source": "src:B", "record_date": "2026-11-02", "tags": "前端,UI"},
            {"id": 3, "title": "任务C", "content": "内容C", "source": "src:C", "record_date": "2026-11-01", "tags": "后端,数据库"},
        ]
        draft = _generate_draft(records)
        assert "### 后端" in draft
        assert "### 前端" in draft
        assert "#1" in draft
        assert "#2" in draft
        assert "#3" in draft
        assert "2026-11-01 ~ 2026-11-02" in draft
