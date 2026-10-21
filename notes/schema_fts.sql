-- The full-text search index (SQLite's FTS5), used by search.py.
--
-- content='notes' makes it an "external content" index: it keeps only the
-- search data and reads the text itself from the notes table. The porter
-- tokenizer matches word endings, so "running" also finds "run".
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5 (
  title, body,
  content = 'notes', content_rowid = 'id',
  tokenize = 'porter unicode61'
);

-- Triggers keep the index in step with the notes table: SQLite runs them
-- after every insert, delete and update, so Python never has to remember.
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts (rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts (notes_fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
END;

-- Only when the text changes: pinning a note doesn't touch the index.
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE OF title, body ON notes BEGIN
  INSERT INTO notes_fts (notes_fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
  INSERT INTO notes_fts (rowid, title, body) VALUES (new.id, new.title, new.body);
END;
