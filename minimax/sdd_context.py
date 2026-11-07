"""Import engineering evidence into seekdb and assemble an SDD task context."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent.resolve()
SOURCES = {"spec": ROOT / "sample/spec.md", "code": ROOT / "sample/pricing.py", "test": ROOT / "sample/test_pricing.py"}


def db():
    import pymysql
    return pymysql.connect(host=os.environ.get("SEEKDB_HOST", "127.0.0.1"),
                           port=int(os.environ.get("SEEKDB_PORT", "2881")),
                           user=os.environ.get("SEEKDB_USER", "root"),
                           password=os.environ.get("SEEKDB_PASSWORD", ""),
                           database=os.environ.get("SEEKDB_DATABASE", "sdd_context"),
                           charset="utf8mb4", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)


def pc(path, payload):
    base = os.environ["POWERCONTEXT_URL"].rstrip("/")
    headers = {"Content-Type": "application/json"}
    if os.environ.get("POWERCONTEXT_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["POWERCONTEXT_TOKEN"]
    req = Request(base + path, json.dumps(payload).encode(), headers, method="POST")
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def initialize(conn):
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS sdd_sources (
            path VARCHAR(255) PRIMARY KEY, kind VARCHAR(16) NOT NULL,
            sha256 CHAR(64) NOT NULL, content LONGTEXT NOT NULL)""")


def import_sources(conn):
    initialize(conn)
    with conn.cursor() as cur:
        for kind, path in SOURCES.items():
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode()).hexdigest()
            cur.execute("""INSERT INTO sdd_sources(path,kind,sha256,content)
                VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                kind=VALUES(kind),sha256=VALUES(sha256),content=VALUES(content)""",
                (str(path.relative_to(ROOT)), kind, digest, content))


def context(conn, task):
    # Sources are read from seekdb on every invocation, so a re-imported specification
    # replaces its previous version in the next task context.
    terms = [word.lower() for word in task.split() if len(word) > 2][:12]
    with conn.cursor() as cur:
        cur.execute("SELECT path,kind,sha256,content FROM sdd_sources")
        rows = cur.fetchall()
    # The query supplies the records; deterministic local ranking keeps every source type.
    rows = sorted(rows, key=lambda row: (-sum(t in row["content"].lower() for t in terms), row["kind"], row["path"]))
    selected = []
    for kind in ("spec", "code", "test"):
        selected.extend(row for row in rows if row["kind"] == kind)
    saved = pc("/v1/memory/search", {"scope_id": os.environ["POWERCONTEXT_SCOPE_ID"], "query": task, "limit": 5})
    progress = [hit["text"] for hit in saved.get("hits", []) if isinstance(hit.get("text"), str)]
    # This is the actual input to the coding assistant. Persisted progress is part
    # of the input, rather than merely an unused API response in a diagnostic field.
    assistant_context = "\n".join(
        [f"Development task: {task}", "Current engineering sources:"]
        + [f"[{row['kind']}] {row['path']} sha256={row['sha256']}\n{row['content']}" for row in selected]
        + ["Saved task progress:"] + progress
    )
    return {"task": task, "sources": selected, "saved_progress": progress,
            "assistant_context": assistant_context, "database_query": "SELECT path,kind,sha256,content FROM sdd_sources"}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import")
    ctx = sub.add_parser("context"); ctx.add_argument("task")
    remember = sub.add_parser("remember"); remember.add_argument("text")
    args = parser.parse_args()
    if args.command == "remember":
        result = pc("/v1/memory/remember", {"scope_id": os.environ["POWERCONTEXT_SCOPE_ID"], "kind": "decision", "text": args.text})
    else:
        with db() as conn:
            result = import_sources(conn) if args.command == "import" else context(conn, args.task)
        if result is None:
            result = {"imported": [str(path.relative_to(ROOT)) for path in SOURCES.values()]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
