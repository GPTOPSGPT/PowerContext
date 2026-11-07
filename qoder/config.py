import os
from dotenv import load_dotenv

load_dotenv()


def get_db_config():
    """Return seekdb connection config from environment variables."""
    required = ["SEEKDB_HOST", "SEEKDB_PORT", "SEEKDB_USER", "SEEKDB_PASSWORD", "SEEKDB_DATABASE"]
    missing = [k for k in required if k not in os.environ or (k != "SEEKDB_PASSWORD" and not os.environ[k])]
    if missing:
        raise RuntimeError(
            f"缺少必要的环境变量: {', '.join(missing)}。"
            f"请复制 .env.example 为 .env 并填入 seekdb 连接信息。"
        )
    return {
        "host": os.environ["SEEKDB_HOST"],
        "port": int(os.environ["SEEKDB_PORT"]),
        "user": os.environ["SEEKDB_USER"],
        "password": os.environ["SEEKDB_PASSWORD"],
        "database": os.environ["SEEKDB_DATABASE"],
        "charset": "utf8mb4",
        "cursorclass": None,
    }
