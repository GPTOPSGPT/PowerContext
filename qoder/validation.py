import re
from datetime import date, datetime

MAX_TITLE_LEN = 500
MAX_CONTENT_LEN = 100000
MAX_SOURCE_LEN = 1000
MAX_TAGS_LEN = 1000


def validate_record(data: dict) -> tuple[dict | None, str | None]:
    """Validate and sanitize a record dict. Returns (cleaned_data, error_msg)."""
    errors = []

    title = (data.get("title") or "").strip()
    if not title:
        errors.append("标题不能为空")
    elif len(title) > MAX_TITLE_LEN:
        errors.append(f"标题长度不能超过 {MAX_TITLE_LEN} 字符")

    content = (data.get("content") or "").strip()
    if not content:
        errors.append("正文不能为空")
    elif len(content) > MAX_CONTENT_LEN:
        errors.append(f"正文长度不能超过 {MAX_CONTENT_LEN} 字符")

    source = (data.get("source") or "").strip()
    if not source:
        errors.append("来源不能为空")
    elif len(source) > MAX_SOURCE_LEN:
        errors.append(f"来源长度不能超过 {MAX_SOURCE_LEN} 字符")

    record_date_raw = (data.get("record_date") or "").strip()
    record_date = None
    if not record_date_raw:
        errors.append("日期不能为空")
    else:
        try:
            record_date = datetime.strptime(record_date_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("日期格式无效，请使用 YYYY-MM-DD")

    tags = (data.get("tags") or "").strip()
    if len(tags) > MAX_TAGS_LEN:
        errors.append(f"标签长度不能超过 {MAX_TAGS_LEN} 字符")

    if errors:
        return None, "；".join(errors)

    return {
        "title": title,
        "content": content,
        "source": source,
        "record_date": record_date,
        "tags": tags,
    }, None


def validate_search_params(keyword: str, date_from: str, date_to: str) -> tuple[str | None, date | None, date | None, str | None]:
    """Validate search parameters. Returns (keyword, date_from, date_to, error)."""
    keyword = (keyword or "").strip()
    if len(keyword) > 200:
        return None, None, None, "关键词长度不能超过 200 字符"

    d_from = None
    if date_from:
        try:
            d_from = datetime.strptime(date_from.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None, None, None, "起始日期格式无效，请使用 YYYY-MM-DD"

    d_to = None
    if date_to:
        try:
            d_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None, None, None, "结束日期格式无效，请使用 YYYY-MM-DD"

    if d_from and d_to and d_from > d_to:
        return None, None, None, "起始日期不能晚于结束日期"

    return keyword or None, d_from, d_to, None
