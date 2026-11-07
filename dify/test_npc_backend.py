import unittest

from npc_backend import play


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.previous = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, args):
        if sql.startswith("SELECT"):
            self.previous = next((row for row in reversed(self.rows) if row[0] == args[0]), None)
        else:
            self.rows.append((args[0], args[1], args[2]))

    def fetchone(self):
        return self.previous[1:] if self.previous else None


class Connection:
    def __init__(self):
        self.rows = []

    def cursor(self):
        return Cursor(self.rows)

    def commit(self):
        pass


class NpcTest(unittest.TestCase):
    def test_previous_prank_is_reused(self):
        db = Connection()
        first = play(db, "p", "藏闹钟")
        second = play(db, "p", "换键盘")
        self.assertIsNone(first["previous_prank"])
        self.assertEqual(second["previous_prank"], "藏闹钟")
        self.assertIn("藏闹钟", second["reaction"])
        self.assertEqual(len(db.rows), 2)

    def test_rejects_empty_player(self):
        with self.assertRaises(ValueError):
            play(Connection(), "  ", "ok")


if __name__ == "__main__":
    unittest.main()
