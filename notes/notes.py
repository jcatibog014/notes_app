"""Notes: the home page, the editor, and everything you can do to a note.

Every query filters on user_id = g.user["id"], so nobody can see or change
someone else's notes, even by typing a note's id into the address bar.
"""
import re
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from .auth import require_login
from .db import get_db
from .markdown import (checklist_progress, find_hashtags, find_wikilinks, parse_markdown_file,
                       reading_minutes, render, to_markdown_file, toggle_checkbox, word_count)
from .search import find_notes
from .tags import prune_tags, save_tags, tag_color, tag_counts, tags_by_note
from .validation import NOTE_COLORS, TITLE_MAX, capitalize_first, validate_note

bp = Blueprint("notes", __name__)
bp.before_request(require_login)

# The views in the sidebar: name -> (heading, the SQL that picks their notes).
# The SQL is written here, never taken from the user, so it's safe to paste
# into a query.
VIEWS = {
    "all": ("Notes", "notes.deleted_at IS NULL AND notes.archived = 0"),
    "pinned": ("Pinned", "notes.deleted_at IS NULL AND notes.archived = 0 AND notes.pinned = 1"),
    "archive": ("Archive", "notes.deleted_at IS NULL AND notes.archived = 1"),
    "trash": ("Trash", "notes.deleted_at IS NOT NULL"),
}
TRASH_DAYS = 30
# Cards show the start of a long note, not all of it.
PREVIEW_CHARS = 900
PREVIEW_LINES = 18


# ---------- Helpers ----------

def now():
    """The current time. Tests set config["NOW"] to a fixed moment."""
    return current_app.config["NOW"]()


def timestamp(moment=None):
    """'YYYY-MM-DD HH:MM:SS': as text, earlier times sort before later ones."""
    return (moment or now()).strftime("%Y-%m-%d %H:%M:%S")


def is_fetch():
    """True when JavaScript sent the request with fetch(), not a normal form.

    static/app.js adds this header, so the server can answer with a little
    JSON instead of a whole page.
    """
    return request.headers.get("X-Requested-With") == "fetch"


def notify(message, category="message"):
    """flash() a message for the next page. fetch() calls show their own feedback."""
    if not is_fetch():
        flash(message, category)


def get_note_or_404(note_id):
    # "AND user_id = ?" means someone else's note is "not found" too.
    note = get_db().execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, g.user["id"])
    ).fetchone()
    if note is None:
        abort(404, "That note doesn't exist, or it isn't yours.")
    return note


def list_args():
    """The current view, search and tag, to keep in links and redirects."""
    args = {}
    view = request.values.get("view", "all")
    if view in VIEWS and view != "all":
        args["view"] = view
    for key in ["q", "tag"]:
        if value := request.values.get(key, "").strip():
            args[key] = value
    return args


def go_back(note_id=None):
    """Where to go after an action: back to the page the form was on.

    Forms in the editor send a hidden next=editor. fetch() calls get an
    empty "204 No Content" answer instead of a page.
    """
    if is_fetch():
        return "", 204
    if request.form.get("next") == "editor" and note_id:
        return redirect(url_for("notes.edit", note_id=note_id))
    return redirect(url_for("notes.index", **list_args()))


def display_title(note):
    return note["title"] or "Untitled"


def title_index():
    """{casefolded title: note id} for the user's notes, made once per request.

    [[Links]] and backlinks match titles without caring about case:
    casefold() is lower() that also handles letters like the German ß.
    """
    if "title_index" not in g:
        rows = get_db().execute(
            "SELECT id, title FROM notes WHERE user_id = ? AND deleted_at IS NULL AND title != ''"
            " ORDER BY updated_at",  # if two notes share a title, the newest wins
            (g.user["id"],),
        ).fetchall()
        g.title_index = {row["title"].casefold(): row["id"] for row in rows}
    return g.title_index


def note_link(title):
    """For [[Title]]: (link, exists). A missing note links to "make it"."""
    note_id = title_index().get(title.casefold())
    if note_id:
        return url_for("notes.edit", note_id=note_id), True
    return url_for("notes.new", title=title[:TITLE_MAX]), False


def tag_url(name):
    return url_for("notes.index", tag=name)


def render_note(body):
    return render(body, note_link=note_link, tag_url=tag_url)


def preview_source(body):
    """The start of a long note, cut at a line break, for its card."""
    text = "\n".join(body.split("\n")[:PREVIEW_LINES])
    if len(text) > PREVIEW_CHARS:
        cut = text[:PREVIEW_CHARS]
        # End at the last whole line, or mid-line with "…" if it's one long line.
        text = cut.rsplit("\n", 1)[0] if "\n" in cut else cut + "…"
    return text


def note_stats(body):
    words = word_count(body)
    done, total = checklist_progress(body)
    return {
        "words": words,
        "minutes": reading_minutes(words),
        "done": done,
        "total": total,
        "percent": round(done * 100 / total) if total else 0,
    }


def decorate(rows):
    """Turn note rows into dicts with what the cards show: tags, preview, stats."""
    notes = [dict(row) for row in rows]
    tags = tags_by_note(get_db(), [note["id"] for note in notes])
    for note in notes:
        note["tags"] = tags[note["id"]]
        note["display_title"] = display_title(note)
        preview = preview_source(note["body"])
        note["preview_html"] = render_note(preview)
        note["cut"] = preview != note["body"]  # cards of cut notes fade out at the bottom
        note.update(note_stats(note["body"]))
    return notes


def ago(stamp):
    """'YYYY-MM-DD HH:MM:SS' -> "Just now", "5 min ago", "Yesterday", "Oct 3"..."""
    moment = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    current = now()
    seconds = (current - moment).total_seconds()
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if moment.date() == current.date():
        return f"{int(seconds // 3600)} h ago"
    days = (current.date() - moment.date()).days
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    if moment.year == current.year:
        return f"{moment:%b} {moment.day}"
    return f"{moment:%b} {moment.day}, {moment.year}"


def greeting():
    hour = now().hour
    part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    name = g.user["display_name"] or g.user["username"]
    return f"Good {part}, {name}"


def purge_old_trash():
    """Delete notes that have been in the Trash for more than TRASH_DAYS days."""
    cutoff = timestamp(now() - timedelta(days=TRASH_DAYS))
    delete_notes("deleted_at IS NOT NULL AND deleted_at < ?", [cutoff])


def delete_notes(where, params):
    """Delete the user's notes that match `where`, for good. Returns how many.

    Rows that point to a note (its tag links and [[links]]) go first, so
    nothing is left pointing at a note that's gone.
    """
    db = get_db()
    ids = [row["id"] for row in db.execute(
        f"SELECT id FROM notes WHERE user_id = ? AND {where}", [g.user["id"], *params]
    )]
    if ids:
        marks = ", ".join("?" for _ in ids)
        db.execute(f"DELETE FROM note_tags WHERE note_id IN ({marks})", ids)
        db.execute(f"DELETE FROM note_links WHERE from_id IN ({marks})", ids)
        db.execute(f"DELETE FROM notes WHERE id IN ({marks})", ids)
        prune_tags(db, g.user["id"])
        db.commit()
    return len(ids)


def save_links(db, note_id, body):
    """Remember which notes this one links to with [[Title]] (for backlinks)."""
    db.execute("DELETE FROM note_links WHERE from_id = ?", (note_id,))
    for title in find_wikilinks(body):
        db.execute("INSERT OR IGNORE INTO note_links (from_id, to_title) VALUES (?, ?)",
                   (note_id, title.casefold()))


def all_tags(data):
    """The tags typed in the tag box, plus the #tags written in the text."""
    tags = list(data["tags"])
    for name in find_hashtags(data["body"]):
        if name not in tags:
            tags.append(name)
    return tags


def insert_note(data, created_at=None):
    """Save a new note with its tags and links. Returns its id."""
    db = get_db()
    stamp = created_at or timestamp()
    cursor = db.execute(
        "INSERT INTO notes (user_id, title, body, color, pinned, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (g.user["id"], data["title"], data["body"], data["color"], data["pinned"], stamp, stamp),
    )
    note_id = cursor.lastrowid
    save_tags(db, g.user["id"], note_id, all_tags(data))
    save_links(db, note_id, data["body"])
    db.commit()
    return note_id


@bp.app_context_processor
def template_values():
    """Values every template can use: the sidebar's counts and tags, and helpers."""
    values = {"keep": list_args(), "tag_color": tag_color, "note_colors": NOTE_COLORS, "views": VIEWS}
    if g.get("user"):
        db = get_db()
        counts = db.execute(
            "SELECT COALESCE(SUM(deleted_at IS NULL AND archived = 0), 0) AS \"all\","
            " COALESCE(SUM(deleted_at IS NULL AND archived = 0 AND pinned = 1), 0) AS pinned,"
            " COALESCE(SUM(deleted_at IS NULL AND archived = 1), 0) AS archive,"
            " COALESCE(SUM(deleted_at IS NOT NULL), 0) AS trash"
            " FROM notes WHERE user_id = ?",
            (g.user["id"],),
        ).fetchone()
        values["view_counts"] = dict(counts)
        values["sidebar_tags"] = [tag for tag in tag_counts(db, g.user["id"]) if tag["count"]]
    return values


bp.add_app_template_filter(ago, "ago")


@bp.app_errorhandler(400)
@bp.app_errorhandler(404)
@bp.app_errorhandler(413)
def error_page(e):
    if is_fetch():
        return jsonify(error=e.description), e.code
    return render_template("error.html", error=e), e.code


# ---------- Read ----------

@bp.get("/")
def index():
    view = request.args.get("view", "all")
    if view not in VIEWS:
        view = "all"
    q = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip().lower() or None
    if view == "trash":
        purge_old_trash()

    heading, where = VIEWS[view]
    rows, query = find_notes(get_db(), g.user["id"], where, q, tag, current_app.config["USE_FTS"])
    notes = decorate(rows)
    for note, row in zip(notes, rows):
        # Search results come with their matches marked (see search.py).
        note["title_html"] = row.get("title_html")
        note["snippet_html"] = row.get("snippet_html")

    # On the main page, pinned notes get their own section on top.
    pinned, others = [], notes
    if view == "all" and not q:
        pinned = [note for note in notes if note["pinned"]]
        others = [note for note in notes if not note["pinned"]]
    return render_template(
        "index.html", view=view, heading=heading, q=q, tag=tag, query=query,
        notes=notes, pinned=pinned, others=others, greeting=greeting(), trash_days=TRASH_DAYS,
    )


# ---------- Create and edit ----------

def render_editor(note, form, errors=None, backlinks=()):
    """The editor page. With errors, it answers 400 and keeps what was typed."""
    stats = note_stats(form.get("body", ""))
    html = render_template(
        "editor.html", note=note, form=form, errors=errors or {}, stats=stats,
        backlinks=backlinks, preview_html=render_note(form.get("body", "")),
        title_max=TITLE_MAX, user_tags=[tag["name"] for tag in tag_counts(get_db(), g.user["id"])],
    )
    return html, 400 if errors else 200


def saved_json(note_id, data):
    """What autosave gets back: where the note lives, and its fresh stats."""
    return jsonify(
        id=note_id,
        url=url_for("notes.edit", note_id=note_id),
        save_url=url_for("notes.save", note_id=note_id),
        tags=all_tags(data),
        **note_stats(data["body"]),
    )


@bp.get("/notes/new")
def new():
    # A [[link]] to a note that doesn't exist yet opens this with its title,
    # and "New Note" inside a tag's page starts with that tag.
    form = {
        "title": capitalize_first(" ".join(request.args.get("title", "").split()))[:TITLE_MAX],
        "body": "",
        "tags": request.args.get("tag", ""),
        "color": "default",
        "pinned": 0,
    }
    return render_editor(None, form)


@bp.post("/notes/new")
def create():
    data, errors = validate_note(request.form)
    if errors:
        if is_fetch():
            return jsonify(errors=errors), 400
        return render_editor(None, request.form, errors)
    note_id = insert_note(data)
    if is_fetch():
        return saved_json(note_id, data), 201
    notify("Note saved.")
    # The quick-capture box on the home page stays on the home page.
    if request.form.get("next") == "index":
        return redirect(url_for("notes.index"))
    return redirect(url_for("notes.edit", note_id=note_id))


def backlinks_of(note):
    """The notes that link to this one with [[its title]]."""
    if not note["title"]:
        return []
    return get_db().execute(
        "SELECT notes.id, notes.title, notes.color FROM note_links JOIN notes ON notes.id = note_links.from_id"
        " WHERE note_links.to_title = ? AND notes.user_id = ? AND notes.deleted_at IS NULL AND notes.id != ?"
        " ORDER BY notes.updated_at DESC",
        (note["title"].casefold(), g.user["id"], note["id"]),
    ).fetchall()


@bp.get("/notes/<int:note_id>")
def edit(note_id):
    note = get_note_or_404(note_id)
    tags = tags_by_note(get_db(), [note_id])[note_id]
    # The tag box shows only the tags typed into it. #tags in the text are
    # already on screen, and come from the text on every save.
    hashtags = find_hashtags(note["body"])
    form = dict(note)
    form["tags"] = ", ".join(tag for tag in tags if tag not in hashtags)
    return render_editor(note, form, backlinks=backlinks_of(note))


@bp.post("/notes/<int:note_id>")
def save(note_id):
    note = get_note_or_404(note_id)
    if note["deleted_at"]:
        abort(400, "This note is in the Trash. Restore it to edit it.")
    data, errors = validate_note(request.form)
    if errors:
        if is_fetch():
            return jsonify(errors=errors), 400
        return render_editor(note, request.form, errors, backlinks_of(note))

    db = get_db()
    db.execute(
        "UPDATE notes SET title = ?, body = ?, color = ?, pinned = ?, updated_at = ?"
        " WHERE id = ? AND user_id = ?",
        (data["title"], data["body"], data["color"], data["pinned"], timestamp(), note_id, g.user["id"]),
    )
    save_tags(db, g.user["id"], note_id, all_tags(data))
    save_links(db, note_id, data["body"])
    db.commit()
    if is_fetch():
        return saved_json(note_id, data)
    notify("Note saved.")
    return redirect(url_for("notes.edit", note_id=note_id))


@bp.post("/preview")
def preview():
    """The editor's Preview: Markdown in, HTML out (the same renderer as the cards)."""
    return render_note(request.form.get("body", "").replace("\r\n", "\n").rstrip())


@bp.post("/notes/<int:note_id>/duplicate")
def duplicate(note_id):
    note = get_note_or_404(note_id)
    tags = tags_by_note(get_db(), [note_id])[note_id]
    copy_title = f"{display_title(note)} (copy)"[:TITLE_MAX]
    new_id = insert_note({"title": copy_title, "body": note["body"], "tags": tags,
                          "color": note["color"], "pinned": 0})
    notify("Made a copy. You're editing the copy now.")
    return redirect(url_for("notes.edit", note_id=new_id))


# ---------- Quick actions: pin, color, archive, checkboxes ----------

@bp.post("/notes/<int:note_id>/pin")
def toggle_pin(note_id):
    note = get_note_or_404(note_id)
    db = get_db()
    db.execute("UPDATE notes SET pinned = ? WHERE id = ?", (0 if note["pinned"] else 1, note_id))
    db.commit()
    notify(f"Unpinned “{display_title(note)}”." if note["pinned"] else f"Pinned “{display_title(note)}”.")
    return go_back(note_id)


@bp.post("/notes/<int:note_id>/color")
def change_color(note_id):
    get_note_or_404(note_id)
    color = request.form.get("color", "")
    if color not in NOTE_COLORS:
        abort(400, "Pick one of the colors.")
    db = get_db()
    db.execute("UPDATE notes SET color = ? WHERE id = ?", (color, note_id))
    db.commit()
    return go_back(note_id)


@bp.post("/notes/<int:note_id>/archive")
def toggle_archive(note_id):
    note = get_note_or_404(note_id)
    db = get_db()
    # Archiving also unpins: a pinned note you've put away would be odd.
    db.execute("UPDATE notes SET archived = ?, pinned = 0 WHERE id = ?", (0 if note["archived"] else 1, note_id))
    db.commit()
    if note["archived"]:
        notify(f"Moved “{display_title(note)}” back to your notes.")
    else:
        notify(f"Archived “{display_title(note)}”.")
    return go_back(note_id)


@bp.post("/notes/<int:note_id>/check")
def check(note_id):
    """Tick or untick one "- [ ]" checkbox, from a card or the editor's preview."""
    note = get_note_or_404(note_id)
    if note["deleted_at"]:
        abort(400, "This note is in the Trash. Restore it to edit it.")
    line = request.form.get("line", "")
    body = toggle_checkbox(note["body"], int(line)) if line.isdigit() else None
    if body is None:
        abort(400, "That checkbox has moved. Reload the page and try again.")
    db = get_db()
    db.execute("UPDATE notes SET body = ?, updated_at = ? WHERE id = ?", (body, timestamp(), note_id))
    db.commit()
    if is_fetch():
        done, total = checklist_progress(body)
        return jsonify(done=done, total=total)
    return go_back(note_id)


# ---------- Trash ----------

@bp.post("/notes/<int:note_id>/trash")
def trash(note_id):
    note = get_note_or_404(note_id)
    db = get_db()
    db.execute("UPDATE notes SET deleted_at = ?, pinned = 0 WHERE id = ?", (timestamp(), note_id))
    db.commit()
    # The "undo:<id>" category shows an Undo button in the toast (base.html).
    notify(f"Moved “{display_title(note)}” to the Trash.", f"undo:{note_id}")
    if is_fetch():
        return "", 204
    # The editor of a note in the Trash isn't much use, so go to the list.
    return redirect(url_for("notes.index", **list_args()))


@bp.post("/notes/<int:note_id>/restore")
def restore(note_id):
    note = get_note_or_404(note_id)
    db = get_db()
    db.execute("UPDATE notes SET deleted_at = NULL WHERE id = ?", (note_id,))
    db.commit()
    notify(f"Restored “{display_title(note)}”.")
    return go_back(note_id)


@bp.post("/notes/<int:note_id>/purge")
def purge(note_id):
    """Delete a note for good. Only from the Trash, so it always takes two steps."""
    note = get_note_or_404(note_id)
    if not note["deleted_at"]:
        abort(400, "Move the note to the Trash first.")
    delete_notes("id = ?", [note_id])
    notify(f"Deleted “{display_title(note)}” forever.")
    return redirect(url_for("notes.index", view="trash"))


@bp.post("/trash/empty")
def empty_trash():
    count = delete_notes("deleted_at IS NOT NULL", [])
    notify(f"Emptied the Trash ({count} {'note' if count == 1 else 'notes'})." if count else "The Trash was already empty.")
    return redirect(url_for("notes.index", view="trash"))


# ---------- Export and import ----------

def file_name(title):
    """A safe file name from a title: "Trip: Day 1!" -> "trip-day-1.md"."""
    slug = re.sub(r"[^\w]+", "-", title.lower(), flags=re.UNICODE).strip("-")
    return (slug[:60] or "note") + ".md"


@bp.get("/notes/<int:note_id>/export")
def export(note_id):
    note = get_note_or_404(note_id)
    tags = tags_by_note(get_db(), [note_id])[note_id]
    text = to_markdown_file(display_title(note), tags, note["body"])
    # "attachment" makes the browser save the file instead of showing it.
    return Response(text, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{file_name(display_title(note))}"'})


@bp.post("/notes/import")
def import_notes():
    """Make a note from each .md or .txt file picked."""
    files = [file for file in request.files.getlist("files") if file.filename]
    if not files:
        notify("Pick one or more .md files to import.", "error")
        return redirect(url_for("notes.index"))
    imported, skipped = 0, []
    for file in files:
        if not re.search(r"\.(md|markdown|txt)$", file.filename, re.IGNORECASE):
            skipped.append(file.filename)
            continue
        try:
            text = file.read().decode("utf-8")
        except UnicodeDecodeError:
            skipped.append(file.filename)
            continue
        title, tags, body = parse_markdown_file(text, file.filename)
        data, errors = validate_note({"title": title[:TITLE_MAX], "body": body, "tags": ", ".join(tags)})
        if errors.get("tags"):  # keep the note, drop tags that don't fit the rules
            data["tags"] = []
            del errors["tags"]
        if errors:
            skipped.append(file.filename)
            continue
        insert_note(data)
        imported += 1
    if imported:
        notify(f"Imported {imported} {'note' if imported == 1 else 'notes'}.")
    if skipped:
        notify(f"Skipped {', '.join(skipped)}: not a text file, empty, or too big.", "error")
    return redirect(url_for("notes.index"))
