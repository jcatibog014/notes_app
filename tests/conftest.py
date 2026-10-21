"""Shared test setup (pytest finds fixtures in this file automatically)."""
from datetime import datetime

import pytest
from werkzeug.security import generate_password_hash

from notes import create_app
from notes.db import get_db

# Every test pretends it's this moment, so "2 h ago" and the 30-day Trash
# never depend on when the tests run.
NOW = datetime(2026, 10, 20, 9, 0, 0)
STAMP = "2026-10-20 08:00:00"  # an hour before NOW: the default for test notes
CSRF = "test-token"

# Every test starts with this account, logged in. Hashing is slow on
# purpose, so the hash is made once here instead of in every test.
USERNAME = "alice"
PASSWORD = "correct horse"
PASSWORD_HASH = generate_password_hash(PASSWORD)


def make_app(tmp_path, **config):
    """An app with a fresh, empty database (plus alice) in tmp_path."""
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.sqlite"),
        "NOW": lambda: NOW,
        **config,
    })
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (USERNAME, PASSWORD_HASH))
        db.commit()
    return app


def logged_in_client(app):
    client = app.test_client()
    # Put a known CSRF token in the session, so post() can send it, and log
    # in as alice (user 1) the same way auth.log_in() does.
    with client.session_transaction() as session:
        session["csrf_token"] = CSRF
        session["user_id"] = 1
    return client


@pytest.fixture
def app(tmp_path):
    # tmp_path is a fresh, empty folder for each test.
    return make_app(tmp_path)


@pytest.fixture
def client(app):
    return logged_in_client(app)


@pytest.fixture
def guest(client):
    """The same test client, logged out."""
    with client.session_transaction() as session:
        del session["user_id"]
    return client


@pytest.fixture
def other_user(app):
    """Create a second account, bob, and return its id."""
    with app.app_context():
        db = get_db()
        cursor = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("bob", PASSWORD_HASH))
        db.commit()
        return cursor.lastrowid


@pytest.fixture
def post(client):
    """client.post() that also sends the CSRF token, like a real form does."""
    def _post(url, data=None, **kwargs):
        return client.post(url, data={"csrf_token": CSRF, **(data or {})}, **kwargs)
    return _post


@pytest.fixture
def fetch_post(client):
    """post() as app.js sends it: with the fetch header, so the answer is JSON or 204."""
    def _post(url, data=None):
        return client.post(url, data={"csrf_token": CSRF, **(data or {})},
                           headers={"X-Requested-With": "fetch"})
    return _post


def insert_note(app, title="", body="", user_id=1, tags=(), **columns):
    """Insert a note straight into the database and return its id.

    This skips validation, so tests can make notes that are already in the
    Trash or written long ago. Other columns can be given too, like pinned=1.
    """
    columns = {"user_id": user_id, "title": title, "body": body,
               "created_at": STAMP, "updated_at": STAMP, **columns}
    # The column names come from the test code, not from a user, so it's
    # safe to paste them into the SQL. The values still use ?.
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    with app.app_context():
        db = get_db()
        note_id = db.execute(f"INSERT INTO notes ({names}) VALUES ({marks})", list(columns.values())).lastrowid
        for name in tags:
            db.execute("INSERT OR IGNORE INTO tags (user_id, name) VALUES (?, ?)", (user_id, name))
            tag_id = db.execute("SELECT id FROM tags WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()["id"]
            db.execute("INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)", (note_id, tag_id))
        db.commit()
        return note_id


@pytest.fixture
def add(app):
    """insert_note() for this test's app. Notes belong to alice unless user_id says otherwise."""
    return lambda *args, **kwargs: insert_note(app, *args, **kwargs)


@pytest.fixture
def fetch(app):
    """Read one note from the database (None if it doesn't exist)."""
    def _fetch(note_id):
        with app.app_context():
            row = get_db().execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            return dict(row) if row else None
    return _fetch


@pytest.fixture
def tags_of(app):
    """The tag names on one note, sorted."""
    def _tags_of(note_id):
        with app.app_context():
            rows = get_db().execute(
                "SELECT tags.name FROM note_tags JOIN tags ON tags.id = note_tags.tag_id"
                " WHERE note_tags.note_id = ? ORDER BY tags.name",
                (note_id,),
            ).fetchall()
            return [row["name"] for row in rows]
    return _tags_of


@pytest.fixture
def query(app):
    """Run any SQL on the test database and return the rows."""
    def _query(sql, params=()):
        with app.app_context():
            return [dict(row) for row in get_db().execute(sql, params).fetchall()]
    return _query
