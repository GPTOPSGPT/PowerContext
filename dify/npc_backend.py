"""Small HTTP bridge between Dify's HTTP node and seekdb.

Credentials are read from environment variables, never from the DSL.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def connect():
    import pymysql

    return pymysql.connect(
        host=os.environ.get("SEEKDB_HOST", "127.0.0.1"),
        port=int(os.environ.get("SEEKDB_PORT", "2881")),
        user=os.environ.get("SEEKDB_USER", "root"),
        password=os.environ.get("SEEKDB_PASSWORD", ""),
        database="dify_prank_npc",
        charset="utf8mb4",
        autocommit=False,
    )


def play(connection, player, prank):
    if not isinstance(player, str) or not 1 <= len(player.strip()) <= 64:
        raise ValueError("player must be 1-64 characters")
    if not isinstance(prank, str) or not 1 <= len(prank.strip()) <= 240:
        raise ValueError("prank must be 1-240 characters")
    player, prank = player.strip(), prank.strip()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT prank, reaction FROM prank_turns WHERE player=%s ORDER BY id DESC LIMIT 1",
            (player,),
        )
        previous = cursor.fetchone()
        if previous:
            reaction = f"你上次用‘{previous[0]}’捉弄我，我还记着呢！这回‘{prank}’也别想蒙混过关。"
        else:
            reaction = f"‘{prank}’？好吧，这次我中招了。下次我一定认出你！"
        cursor.execute(
            "INSERT INTO prank_turns(player, prank, reaction) VALUES (%s, %s, %s)",
            (player, prank, reaction),
        )
    connection.commit()
    return {"player": player, "prank": prank, "previous_prank": previous[0] if previous else None, "reaction": reaction}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/turn":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 4096:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(size))
            with connect() as connection:
                result = play(connection, request.get("player"), request.get("prank"))
            status = 200
        except (ValueError, json.JSONDecodeError) as exc:
            status, result = 400, {"error": str(exc)}
        except Exception:
            self.log_exception()
            status, result = 500, {"error": "database unavailable"}
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_exception(self):
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("NPC_BIND", "127.0.0.1"), int(os.environ.get("NPC_PORT", "8765"))), Handler).serve_forever()
