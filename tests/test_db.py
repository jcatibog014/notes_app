"""Upgrading a database made by an older version of the app."""
import sqlite3

from notes import create_app
from notes.db import get_db

# The users and notes tables as the first version of the app made them.
OLD_SCHEMA = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  display_name TEXT, avatar TEXT, theme TEXT NOT NULL DEFAULT 'default',
  appearance TEXT NOT NULL DEFAULT 'system', is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users (id),
  title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT 'default',
  pinned INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT INTO users (username, password_hash) VALUES ('old_timer', 'x');
INSERT INTO notes (user_id, title, body, created_at, updated_at)
  VALUES (1, 'From before', 'searchable words', '2026-01-01 00:00:00', '2026-01-01 00:00:00');
"""


def test_old_databases_get_the_new_columns(tmp_path):
    path = tmp_path / "old.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(OLD_SCHEMA)
    connection.close()

    app = create_app({"TESTING": True, "DATABASE": str(path)})
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT * FROM users").fetchone()
        assert (user["onboarded"], user["show_greeting"], user["editor_mode"]) == (0, 1, "write")
        assert db.execute("SELECT opened_at FROM notes").fetchone()["opened_at"] is None
        # The search index was built for the notes that were already there.
        if app.config["USE_FTS"]:
            found = db.execute("SELECT rowid FROM notes_fts WHERE notes_fts MATCH 'searchable'").fetchall()
            assert [row[0] for row in found] == [1]
