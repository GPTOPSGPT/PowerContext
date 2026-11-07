import pymysql
from config import get_db_config


def get_connection():
    """Create a new seekdb/MySQL connection."""
    cfg = get_db_config()
    return pymysql.connect(**cfg)


def init_db(conn):
    """Run the schema init script against an existing connection."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                content TEXT NOT NULL,
                source VARCHAR(1000) NOT NULL,
                record_date DATE NOT NULL,
                tags VARCHAR(1000) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_record_date (record_date),
                INDEX idx_tags (tags(255))
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
        """)
    conn.commit()


def insert_record(conn, record: dict) -> int:
    """Insert a single record. Returns the new id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO records (title, content, source, record_date, tags) VALUES (%s, %s, %s, %s, %s)",
            (record["title"], record["content"], record["source"], record["record_date"], record["tags"]),
        )
    conn.commit()
    return cur.lastrowid


def insert_records_batch(conn, records: list[dict]) -> int:
    """Insert multiple records. Returns count inserted."""
    if not records:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO records (title, content, source, record_date, tags) VALUES (%s, %s, %s, %s, %s)",
            [(r["title"], r["content"], r["source"], r["record_date"], r["tags"]) for r in records],
        )
    conn.commit()
    return cur.rowcount


def search_records(conn, keyword=None, date_from=None, date_to=None) -> list[dict]:
    """Search records by keyword and/or date range. All SQL is parameterized."""
    conditions = []
    params = []

    if keyword:
        conditions.append("(title LIKE %s OR content LIKE %s OR tags LIKE %s)")
        like = f"%{keyword}%"
        params.extend([like, like, like])

    if date_from:
        conditions.append("record_date >= %s")
        params.append(date_from)

    if date_to:
        conditions.append("record_date <= %s")
        params.append(date_to)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"SELECT id, title, content, source, record_date, tags FROM records{where} ORDER BY record_date DESC, id DESC"

    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    for row in rows:
        if isinstance(row.get("record_date"), str):
            pass
        elif hasattr(row.get("record_date"), "isoformat"):
            row["record_date"] = row["record_date"].isoformat()

    return rows


def get_record_by_id(conn, record_id: int) -> dict | None:
    """Fetch a single record by ID."""
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("SELECT id, title, content, source, record_date, tags FROM records WHERE id = %s", (record_id,))
        row = cur.fetchone()
    if row and hasattr(row.get("record_date"), "isoformat"):
        row["record_date"] = row["record_date"].isoformat()
    return row


def get_records_by_ids(conn, ids: list[int]) -> list[dict]:
    """Fetch multiple records by their IDs, preserving the given order."""
    if not ids:
        return []
    placeholders = ", ".join(["%s"] * len(ids))
    sql = f"SELECT id, title, content, source, record_date, tags FROM records WHERE id IN ({placeholders})"
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute(sql, ids)
        rows = cur.fetchall()
    id_order = {rid: i for i, rid in enumerate(ids)}
    rows.sort(key=lambda r: id_order.get(r["id"], 999999))
    for row in rows:
        if hasattr(row.get("record_date"), "isoformat"):
            row["record_date"] = row["record_date"].isoformat()
    return rows
