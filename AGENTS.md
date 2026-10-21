# AGENTS.md

This file guides AI coding agents (Claude Code, Codex, Cursor, Copilot and others) working in this repository.

## Overview

Forget-Me-Note, a notes web app in Python (Flask + SQLite, using the stdlib `sqlite3` with no ORM). It is a learning project for CRUD, text handling, search and data modeling. Keep the code readable for a learner: short comments that explain *why*, and no extra libraries (no Markdown package, WTForms or SQLAlchemy) unless the owner asks for them.

Python 3.13 is at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`. Use the virtual environment:

- Install: `.venv\Scripts\python -m pip install -r requirements.txt` (create `.venv` from the full Python path first if it's missing).
- Run: `.venv\Scripts\flask --app notes run --debug`, then open http://127.0.0.1:5000.
- Test: `.venv\Scripts\python -m pytest`.

## Architecture

- `notes/__init__.py` holds `create_app(test_config)`. Config: `DATABASE` (`instance/notes.sqlite`, git-ignored), `NOW` (a function returning the current `datetime`; use `notes.now()` / `notes.timestamp()`, never `datetime.now()`, so tests can fix the time) and `USE_FTS` (`None` = use FTS5 if SQLite has it; `db.py` sets it to `True`/`False`). `add_static_version()` adds `?v=<mtime>` to static links: always link static files with `url_for`.
- `notes/db.py`: `get_db()` keeps one connection per request on `g`, with `row_factory = sqlite3.Row`. `init_db()` runs `schema.sql`, then `schema_fts.sql` (the FTS5 index + triggers) if SQLite has FTS5, and rebuilds a new index from existing notes. A new column in an existing table goes in `schema.sql` and in `NEW_COLUMNS`.
- Data model (`schema.sql`): `users`, `notes` (`deleted_at` set = in the Trash; `archived`, `pinned`, `color`; times are `'YYYY-MM-DD HH:MM:SS'` text), `tags` + `note_tags` (many-to-many), `note_links` (`from_id`, `to_title` casefolded: a `[[link]]` is stored by title so it can point at a note that doesn't exist yet). `notes_fts` is an external-content FTS5 table kept in sync by triggers.
- `notes/auth.py`: `/register`, `/login`, `/logout` (POST). `load_logged_in_user()` sets `g.user`. Blueprints call `bp.before_request(require_login)`.
- `notes/notes.py` (blueprint `notes`):
  - `VIEWS` maps `all`/`pinned`/`archive`/`trash` to a heading and fixed SQL. Every query filters on `user_id = g.user["id"]`; `get_note_or_404()` gives 404 for someone else's note.
  - Save notes with `insert_note(data)` or the UPDATE in `save()`; both call `save_tags()` with `all_tags(data)` (tag box + `#tags` in the text) and `save_links()`. Delete for good with `delete_notes(where, params)`, which removes `note_tags` and `note_links` rows first and prunes unused tags.
  - Delete is a soft delete (`trash()` sets `deleted_at`); `purge_old_trash()` deletes notes older than `TRASH_DAYS` when the Trash is opened. A note in the Trash can't be saved or ticked (400).
  - `is_fetch()` (header `X-Requested-With: fetch`): autosave gets JSON (`saved_json()`), other actions 204. `notify()` flashes only for normal requests. Flash category `undo:<id>` shows an Undo button that restores that note.
  - `go_back()`: `next=editor` returns to the editor, otherwise to the list with `list_args()` (view, q, tag) kept.
  - `decorate()` turns rows into card dicts (tags, `preview_html`, stats). `render_note()` renders Markdown with `[[link]]` and `#tag` URLs.
  - The editor's tag box shows only tags *not* written as `#tags` in the text, so removing a hashtag from the text removes the tag.
- `notes/markdown.py`: the hand-written renderer. `render()` escapes the text first, then adds HTML (block pass, then `render_inline()` with placeholders). Helpers: `plain_text`, `word_count`, `reading_minutes`, `checklist_progress`, `toggle_checkbox` (by line number, matching `data-line` in the HTML), `find_hashtags`, `find_wikilinks`, `rename_hashtag`, `to_markdown_file` / `parse_markdown_file`. Lines inside ``` code blocks are ignored by all of these.
- `notes/search.py`: `find_notes(db, user_id, where, text, tag, use_fts)`. `parse_query()` splits filters (`tag:`, `#tag`, `is:pinned`, `color:`, `has:checklist`, `"phrases"`) from words. FTS words become `"word"*`; results get `title_html`/`snippet_html` with `<mark>` via the `START`/`END` markers and `marked()` (escape first). `search_like()` is the fallback without FTS5.
- `notes/tags.py` (blueprint `tags`): `save_tags`, `prune_tags`, `tags_by_note`, `tag_counts`, `tag_color()` (color from the letters). The Tags page renames (merging into an existing tag) and deletes, and rewrites `#tags` in note text with `rename_hashtag()`.
- `notes/profile.py`: picture, display name, username, password, and theme + appearance (`POST /profile/theme`). The demo account (`users.is_demo = 1`) can't change its username or password.
- `notes/demo.py`: `flask --app notes create-demo` makes or refills a demo account from `DEMO_NOTES`, with a username and password typed at the prompt.
- `notes/validation.py`: `validate_note`, `validate_tag_name`, `validate_registration`, `validate_profile`, `validate_password_change`, `validate_settings`, plus `NOTE_COLORS`, `THEMES`, `APPEARANCES`, `AVATAR_CHOICES`. It must not import Flask.
- `notes/csrf.py`: every POST form needs `{{ ui.csrf() }}`; `app.js` sends the token from `<meta name="csrf-token">`.

## Conventions

- **The logo and app icon are static**: `notes/static/logo.png` (from `logo.svg`, with hard-coded colors), shown with `<img>` and as the favicon/apple-touch-icon. Never theme, filter or recolor it. A theme (`[data-theme]` in `style.css`) changes only `--accent`, `--accent-strong`, `--accent-2` and the page tint. Note colors (`.note-<color>`, `--note-*`) and tag hues are fixed too; dark mode has its own fixed pastels. `tests/test_profile.py` checks the logo in every theme.
- Styling: `notes/static/style.css`, colors as variables on `:root`, dark variables written twice (`dark`, and `system` inside `prefers-color-scheme: dark`). Breakpoints: 900px (sidebar becomes the bottom nav, sheets slide up) and 560px (two-column cards). Icons are the `ui.icon()` macro in `_macros.html`.
- JavaScript (`static/app.js`) only adds to pages that already work without it.
- Capitalization: **Title Case** for buttons, headings, navigation and menu actions; **sentence case** for labels, hints and messages. Titles get `capitalize_first()` on save. Tags are lowercase.
- Always pass SQL values as `?` placeholders. SQL pieces pasted into queries (like `VIEWS`) must come from the code, never from the user.
- Keep comments teaching-oriented but brief. Add or update a test with every behavior change. Tests run with the time fixed to 2026-10-20 09:00 (`tests/conftest.py`); fixtures: `client`, `guest`, `other_user`, `post`, `fetch_post`, `add`, `fetch`, `tags_of`, `query`.
