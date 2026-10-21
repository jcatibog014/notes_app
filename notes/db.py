"""Database helpers.

Each request gets one SQLite connection: get_db() opens it the first time
it's needed and keeps it on `g` (Flask's per-request storage), and
close_db() closes it when the request ends.
"""
import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        # Rows act like dicts, so you can write row["title"] instead of row[1].
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the tables if they don't exist yet. Safe to run again."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))
    add_missing_columns(db)
    if current_app.config["USE_FTS"] is not False:
        current_app.config["USE_FTS"] = init_fts(db)


def init_fts(db):
    """Set up the full-text search index. Returns False if SQLite has no FTS5.

    FTS5 ships with Python's SQLite on Windows and most Linux hosts, but not
    every build has it. Without it, search.py falls back to LIKE.
    """
    existed = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'notes_fts'").fetchone()
    try:
        with current_app.open_resource("schema_fts.sql") as f:
            db.executescript(f.read().decode("utf8"))
    except sqlite3.OperationalError:  # "no such module: fts5"
        return False
    if not existed:
        # A new index starts empty. "rebuild" fills it from the notes that
        # are already there (the triggers only catch changes from now on).
        db.execute("INSERT INTO notes_fts (notes_fts) VALUES ('rebuild')")
        db.commit()
    return True


# Columns added to a table after it was first made, with their SQL types.
# Databases made before them get them added by add_missing_columns().
NEW_COLUMNS = {
    "users": {
        "onboarded": "INTEGER NOT NULL DEFAULT 0",
        "show_greeting": "INTEGER NOT NULL DEFAULT 1",
        "editor_mode": "TEXT NOT NULL DEFAULT 'write'",
        "note_sort": "TEXT NOT NULL DEFAULT 'updated'",
    },
    "notes": {
        "opened_at": "TEXT",
        "position": "INTEGER",
    },
}


def add_missing_columns(db):
    """Upgrade a database made by an older version of the app.

    CREATE TABLE IF NOT EXISTS skips a table that is already there, so an
    old table never gets new columns. Add them by hand.
    """
    for table, new_columns in NEW_COLUMNS.items():
        columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})")]
        for name, sql_type in new_columns.items():
            if name not in columns:
                # Table and column names can't be ? placeholders. These come
                # from the dict above, never from a user, so pasting them in is safe.
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
    db.commit()


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Delete every note and account and start empty.")
def init_db_command(reset):
    """Create the database (flask --app notes init-db [--reset])."""
    if reset:
        click.confirm("Delete ALL notes and accounts?", abort=True)
        db = get_db()
        for name in ["notes_ai", "notes_ad", "notes_au"]:
            db.execute(f"DROP TRIGGER IF EXISTS {name}")
        for table in ["notes_fts", "note_links", "note_tags", "tags", "notes", "users"]:
            db.execute(f"DROP TABLE IF EXISTS {table}")
    init_db()
    click.echo("Database ready.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    # Create the tables on startup, so the app works on its first run.
    with app.app_context():
        init_db()
