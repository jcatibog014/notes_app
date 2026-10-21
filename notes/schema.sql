-- IF NOT EXISTS makes this safe to run on every start.
-- The search index is in schema_fts.sql, because not every SQLite has FTS5.

-- One row per account. The password itself is never stored, only a hash
-- of it (see auth.py).
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,  -- "Ana" and "ana" count as the same name
  password_hash TEXT    NOT NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
  display_name  TEXT,                                -- "Janelle", shown instead of the username; NULL = none
  avatar        TEXT,                                -- an emoji like '🦊', or NULL for the first letter
  theme         TEXT    NOT NULL DEFAULT 'default',  -- one of THEMES in validation.py
  appearance    TEXT    NOT NULL DEFAULT 'system',   -- 'light', 'dark', or 'system' to follow the device
  is_demo       INTEGER NOT NULL DEFAULT 0           -- 1 = the shared demo account (see demo.py)
);

-- Every note belongs to one user, through user_id.
CREATE TABLE IF NOT EXISTS notes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users (id),
  title      TEXT    NOT NULL DEFAULT '',
  body       TEXT    NOT NULL DEFAULT '',            -- Markdown text (see markdown.py)
  color      TEXT    NOT NULL DEFAULT 'default',     -- one of NOTE_COLORS in validation.py
  pinned     INTEGER NOT NULL DEFAULT 0,             -- SQLite has no boolean: 0 = no, 1 = yes
  archived   INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,                                   -- set when moved to the Trash; NULL = not in the Trash
  created_at TEXT    NOT NULL,                       -- 'YYYY-MM-DD HH:MM:SS', set by notes.py
  updated_at TEXT    NOT NULL
);
-- The home page asks for "this user's notes, not in the Trash, pinned first,
-- newest first" on every visit. An index lets SQLite jump straight to them.
CREATE INDEX IF NOT EXISTS notes_by_user ON notes (user_id, deleted_at, archived, pinned, updated_at);

-- Tags are a "many-to-many" link: a note can have many tags, and a tag can
-- be on many notes. So the links get their own table, one row per pair.
CREATE TABLE IF NOT EXISTS tags (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users (id),
  name    TEXT    NOT NULL,                          -- saved in lowercase, without the #
  UNIQUE (user_id, name)                             -- two people can each have #work, one person can't have two
);

CREATE TABLE IF NOT EXISTS note_tags (
  note_id INTEGER NOT NULL REFERENCES notes (id),
  tag_id  INTEGER NOT NULL REFERENCES tags (id),
  PRIMARY KEY (note_id, tag_id)                      -- the same tag can't be on a note twice
);
CREATE INDEX IF NOT EXISTS note_tags_by_tag ON note_tags (tag_id);

-- [[Note title]] links inside a note's text. The target is saved by title
-- (casefolded), not by id, so a link can be written before its note exists
-- and starts working as soon as a note with that title is made.
CREATE TABLE IF NOT EXISTS note_links (
  from_id  INTEGER NOT NULL REFERENCES notes (id),
  to_title TEXT    NOT NULL,
  PRIMARY KEY (from_id, to_title)
);
CREATE INDEX IF NOT EXISTS note_links_by_title ON note_links (to_title);
