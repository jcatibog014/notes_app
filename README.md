<p align="center">
  <img src="notes/static/logo.png" alt="Forget-Me-Note logo: a white note page with a blue forget-me-not flower, on a periwinkle tile" width="140">
</p>

<h1 align="center">Forget-Me-Note</h1>

<p align="center">A calm, colorful notes web app built with <b>Python</b>, <b>Flask</b> and <b>SQLite</b>, made to practice CRUD, text handling, search and data modeling. 🌼<br><i>Little notes, never forgotten.</i></p>

## Screenshots

Your notes as a grid of pastel cards. Pinned notes stay on top, checklists show their progress, and you can tick boxes right on the card.

![Home screen with a grid of colorful note cards](docs/screenshots/home.png)

| The editor: write, split or preview | Search with highlighted matches |
|---|---|
| ![The note editor with a formatting toolbar](docs/screenshots/editor.png) | ![Search results with the matched words highlighted](docs/screenshots/search.png) |

| On a phone | Dark mode (Rose theme) |
|---|---|
| <img src="docs/screenshots/phone.png" alt="Two columns of note cards on a phone, with a bottom navigation bar" width="300"> | ![The home screen in dark mode with the Rose theme](docs/screenshots/dark.png) |

| Profile and themes | Tags |
|---|---|
| ![Profile page with picture, name, password and theme settings](docs/screenshots/profile.png) | ![Tag manager with rename and delete](docs/screenshots/tags.png) |

## Features

- **Accounts**: sign up, log in and log out. Each person sees only their own notes.
- **Notes**: create, edit, copy and delete. A note needs a title *or* some text, not both.
- **Autosave**: the editor saves as you type ("Saving… / Saved ✓"), and once more if you leave the page.
- **Markdown, written by hand** (no library): `# headings`, `**bold**`, `*italic*`, `~~strike~~`, `` `code` ``, code blocks, bulleted and numbered lists, `- [ ]` checkboxes, `> quotes`, links and `---`. Write, Split or Preview mode. Your text is escaped first, so nothing in a note can run as code.
- **Checklists**: tick boxes on the card or in the preview, and see the progress bar fill up.
- **Tags**: type them in the tag box (as chips), or write `#tags` anywhere in the text. Click one in the sidebar to see its notes. The **Tags page** renames (renaming onto an existing tag merges them) and deletes tags, and updates the `#tags` in your text too.
- **Full-text search** with SQLite's FTS5: the best matches come first, matches are highlighted, and `bud` already finds `budget` while you type. Filters: `tag:work` or `#work`, `is:pinned`, `color:blue`, `has:checklist` and `"exact phrases"`. (Without FTS5, a simpler search does the same job.)
- **Links between notes**: write `[[Note title]]`. A link to a note that doesn't exist yet offers to create it, and every note lists the notes that link to it (**Linked From**).
- **Pin** notes to the top, give them one of **8 pastel colors**, and **archive** the ones you want out of the way.
- **Trash**: deleting moves a note to the Trash, with an **Undo** button. Restore it, delete it forever, or empty the Trash. Notes left there are deleted after 30 days.
- **Note stats**: word count, reading time and checklist progress.
- **Import and export**: download a note as a `.md` file (with its title and tags at the top), or import `.md` files.
- **Profile**: pick a picture (an emoji), set the name your greeting uses, change your username or password, and choose a theme: **Forget-Me-Not** (the default), **Lavender**, **Rose**, **Mint**, **Marigold** or **Ink**, in light, dark or matching your device. The logo and app icon always stay the same.
- **Keyboard shortcuts**: `Ctrl K` or `/` search, `N` new note, `Ctrl S` save, `Ctrl B`/`Ctrl I` bold/italic, `Ctrl E` preview, `Esc` back, `?` the list.
- **Nice touches**: a greeting, a quick "Take a note…" box, lists that continue when you press Enter, a bottom bar on phones, and sheets that slide up.

## Setup (Windows, PowerShell)

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\flask --app notes run --debug
```

Then open http://127.0.0.1:5000. The database (`instance/notes.sqlite`) is created on the first run.

To make a demo account full of example notes, run `.venv\Scripts\flask --app notes create-demo` and type a username and password. Run it again to put fresh examples back. To delete every note and account, run `.venv\Scripts\flask --app notes init-db --reset`.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

## Deploy (PythonAnywhere)

PythonAnywhere runs Flask apps for free and keeps the SQLite file between restarts.

1. In a **Bash console**:
   ```bash
   git clone https://github.com/jcatibog014/notes_app
   cd notes_app
   python3.13 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   # Check that this SQLite has full-text search (the app falls back to a simpler search if not):
   .venv/bin/python -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(a)'); print('FTS5 ok')"
   ```
2. On the **Web** tab, add a new web app with **Manual configuration** and **Python 3.13**. Then:
   - **Virtualenv**: `/home/<username>/notes_app/.venv`
   - **Static files**: URL `/static/` → directory `/home/<username>/notes_app/notes/static`
   - **WSGI configuration file**: replace its contents with:
     ```python
     import os, sys
     sys.path.insert(0, "/home/<username>/notes_app")
     os.environ["SECRET_KEY"] = "paste-a-long-random-string-here"  # never commit this
     from notes import create_app
     application = create_app()
     ```
     (Make a random key with `python3.13 -c "import secrets; print(secrets.token_hex(32))"`.)
3. Optional: `.venv/bin/flask --app notes create-demo` in the Bash console.
4. Click **Reload** and open `https://<username>.pythonanywhere.com`.

To update later: `cd notes_app && git pull`, then **Reload** on the Web tab.

## Project layout

```
notes/
  __init__.py     the app factory
  db.py           database connection and setup
  schema.sql      tables: users, notes, tags, note_tags, note_links
  schema_fts.sql  the full-text search index and its triggers
  auth.py         sign up, log in, log out
  notes.py        the home page, editor, trash, import/export
  markdown.py     the hand-written Markdown renderer and text helpers
  search.py       filters, full-text search and highlighting
  tags.py         saving tags, and the Tags page
  profile.py      the profile page
  validation.py   checks for every form
  demo.py         the create-demo command
  templates/      the pages
  static/         style.css, app.js, logo.png, logo.svg
tests/            pytest tests
```
