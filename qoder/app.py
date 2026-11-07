import json
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

from config import get_db_config
from db import get_connection, init_db, insert_record, insert_records_batch, search_records, get_record_by_id, get_records_by_ids
from validation import validate_record, validate_search_params

app = Flask(__name__)
app.secret_key = "evidence-desk-dev-key-change-in-prod"


class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


app.json.encoder = DateEncoder


def _get_conn():
    try:
        conn = get_connection()
        return conn
    except RuntimeError as e:
        raise
    except Exception as e:
        raise RuntimeError(f"无法连接到 seekdb 数据库: {e}") from e


@app.route("/")
def index():
    try:
        conn = _get_conn()
        recent = search_records(conn, date_from=None, date_to=None)[:10]
        conn.close()
    except RuntimeError as e:
        flash(str(e), "error")
        recent = []
    return render_template("index.html", records=recent)


@app.route("/import", methods=["GET", "POST"])
def import_records():
    if request.method == "GET":
        return render_template("import.html")

    raw = request.form.get("json_data", "").strip()
    if not raw:
        flash("请提供 JSON 数据", "error")
        return render_template("import.html"), 400

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        flash(f"JSON 解析失败: {e}", "error")
        return render_template("import.html"), 400

    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        flash("JSON 必须是数组或单个对象", "error")
        return render_template("import.html"), 400

    conn = _get_conn()
    valid_records = []
    errors = []
    for i, item in enumerate(items):
        cleaned, err = validate_record(item)
        if err:
            errors.append(f"第 {i+1} 条: {err}")
        else:
            valid_records.append(cleaned)

    inserted = 0
    if valid_records:
        inserted = insert_records_batch(conn, valid_records)
    conn.close()

    if errors:
        for e in errors:
            flash(e, "warning")

    flash(f"成功导入 {inserted} 条记录", "success")
    return redirect(url_for("import_records"))


@app.route("/search")
def search():
    keyword = request.args.get("q", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    kw_clean, d_from, d_to, err = validate_search_params(keyword, date_from, date_to)
    if err:
        flash(err, "error")
        return render_template("search.html", records=[], keyword=keyword, date_from=date_from, date_to=date_to)

    conn = _get_conn()
    records = search_records(conn, keyword=kw_clean, date_from=d_from, date_to=d_to)
    conn.close()

    return render_template("search.html", records=records, keyword=keyword or "", date_from=date_from, date_to=date_to)


@app.route("/record/<int:record_id>")
def record_detail(record_id):
    conn = _get_conn()
    rec = get_record_by_id(conn, record_id)
    conn.close()
    if not rec:
        flash("记录不存在", "error")
        return redirect(url_for("search"))
    return render_template("record_detail.html", record=rec)


@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "GET":
        selected_ids = request.args.get("ids", "")
        if selected_ids:
            try:
                ids = [int(x.strip()) for x in selected_ids.split(",") if x.strip()]
            except ValueError:
                flash("无效的记录 ID", "error")
                return redirect(url_for("search"))
            conn = _get_conn()
            records = get_records_by_ids(conn, ids)
            conn.close()
        else:
            records = []
        draft = _generate_draft(records)
        return render_template("report.html", records=records, draft=draft)

    record_ids_raw = request.form.get("record_ids", "")
    try:
        ids = [int(x.strip()) for x in record_ids_raw.split(",") if x.strip()]
    except ValueError:
        flash("无效的记录 ID", "error")
        return redirect(url_for("search"))

    conn = _get_conn()
    records = get_records_by_ids(conn, ids)
    conn.close()
    draft = _generate_draft(records)
    return render_template("report.html", records=records, draft=draft)


def _generate_draft(records: list[dict]) -> str:
    """Generate a weekly report draft from selected records."""
    if not records:
        return "请选择至少一条记录来生成周报草稿。"

    dates = sorted(set(r["record_date"] for r in records))
    date_range = f"{dates[0]} ~ {dates[-1]}" if len(dates) > 1 else dates[0]

    lines = [f"# 周报草稿（{date_range}）\n"]
    lines.append("## 本周工作\n")

    tag_groups: dict[str, list[dict]] = {}
    for r in records:
        tags = r.get("tags", "") or "其他"
        primary_tag = tags.split(",")[0].strip() or "其他"
        tag_groups.setdefault(primary_tag, []).append(r)

    for tag, group in tag_groups.items():
        lines.append(f"### {tag}\n")
        for r in group:
            lines.append(f"- **{r['title']}**（{r['record_date']}）")
            lines.append(f"  - 来源：{r['source']}")
            lines.append(f"  - 摘要：{r['content'][:200]}{'...' if len(r['content']) > 200 else ''}")
            lines.append("")

    lines.append("## 涉及记录 ID\n")
    lines.append(", ".join(f"#{r['id']}" for r in records))
    lines.append("")
    lines.append("## 来源汇总\n")
    for r in records:
        lines.append(f"- [{r['id']}] {r['source']}")

    return "\n".join(lines)


@app.route("/api/search")
def api_search():
    keyword = request.args.get("q", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    kw_clean, d_from, d_to, err = validate_search_params(keyword, date_from, date_to)
    if err:
        return jsonify({"error": err}), 400

    conn = _get_conn()
    records = search_records(conn, keyword=kw_clean, date_from=d_from, date_to=d_to)
    conn.close()
    return jsonify({"records": records, "count": len(records)})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5100)
