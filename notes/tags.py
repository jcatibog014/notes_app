"""Tags: saving a note's tags, and the tag manager page.

Tags are a many-to-many link (see schema.sql): `tags` holds each name once
per user, and `note_tags` has one row for each (note, tag) pair.
"""
from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from .auth import require_login
from .db import get_db
from .markdown import rename_hashtag
from .validation import validate_tag_name

bp = Blueprint("tags", __name__)
bp.before_request(require_login)

# Tag chips get a color worked out from their letters (see tag_color()).
TAG_COLORS = ["blue", "purple", "pink", "red", "orange", "yellow", "green", "teal"]


def tag_color(name):
    """The same name always gets the same color, so #home looks the same
    everywhere, without saving a color for every tag."""
    return TAG_COLORS[sum(ord(letter) for letter in name) % len(TAG_COLORS)]


def save_tags(db, user_id, note_id, names):
    """Make the note's tags exactly `names`, creating any new tags."""
    db.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
    for name in names:
        # OR IGNORE: if the user already has this tag, the UNIQUE rule skips
        # the insert, and the SELECT below finds the old one.
        db.execute("INSERT OR IGNORE INTO tags (user_id, name) VALUES (?, ?)", (user_id, name))
        tag_id = db.execute("SELECT id FROM tags WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()["id"]
        db.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)", (note_id, tag_id))
    prune_tags(db, user_id)


def prune_tags(db, user_id):
    """Delete the user's tags that are no longer on any note.

    Notes in the Trash keep their tags, so restoring a note brings them back.
    """
    db.execute("DELETE FROM tags WHERE user_id = ? AND id NOT IN (SELECT tag_id FROM note_tags)", (user_id,))


def tags_by_note(db, note_ids):
    """{note_id: [tag names, A to Z]} for many notes in one query."""
    found = {note_id: [] for note_id in note_ids}
    if not note_ids:
        return found
    rows = db.execute(
        "SELECT note_tags.note_id, tags.name FROM note_tags JOIN tags ON tags.id = note_tags.tag_id"
        f" WHERE note_tags.note_id IN ({', '.join('?' for _ in note_ids)}) ORDER BY tags.name",
        list(note_ids),
    ).fetchall()
    for row in rows:
        found[row["note_id"]].append(row["name"])
    return found


def tag_counts(db, user_id):
    """The user's tags with how many notes (not in the Trash) have each one."""
    return db.execute(
        "SELECT tags.id, tags.name, COUNT(notes.id) AS count FROM tags"
        " LEFT JOIN note_tags ON note_tags.tag_id = tags.id"
        " LEFT JOIN notes ON notes.id = note_tags.note_id AND notes.deleted_at IS NULL"
        " WHERE tags.user_id = ? GROUP BY tags.id ORDER BY tags.name",
        (user_id,),
    ).fetchall()


def get_tag_or_404(tag_id):
    tag = get_db().execute("SELECT * FROM tags WHERE id = ? AND user_id = ?", (tag_id, g.user["id"])).fetchone()
    if tag is None:
        abort(404, "That tag doesn't exist, or it isn't yours.")
    return tag


def rewrite_hashtags(db, tag_id, old, new=None):
    """Change #old in the text of every note with this tag (see rename_hashtag()).

    Otherwise the next save would read "#old" in the text and bring the old
    tag straight back.
    """
    notes = db.execute(
        "SELECT notes.id, notes.body FROM notes JOIN note_tags ON note_tags.note_id = notes.id"
        " WHERE note_tags.tag_id = ?",
        (tag_id,),
    ).fetchall()
    for note in notes:
        body = rename_hashtag(note["body"], old, new)
        if body != note["body"]:
            db.execute("UPDATE notes SET body = ? WHERE id = ?", (body, note["id"]))


@bp.get("/tags")
def index(rename_id=None, rename_value="", error=None, review=None):
    html = render_template(
        "tags.html", tags=tag_counts(get_db(), g.user["id"]),
        rename_id=rename_id, rename_value=rename_value, error=error, review=review,
    )
    return html, 400 if error else 200


def notes_with_tag(db, tag_id):
    """The notes (not in the Trash) that have this tag, newest first."""
    return db.execute(
        "SELECT notes.id, notes.title FROM notes JOIN note_tags ON note_tags.note_id = notes.id"
        " WHERE note_tags.tag_id = ? AND notes.deleted_at IS NULL ORDER BY notes.updated_at DESC",
        (tag_id,),
    ).fetchall()


@bp.post("/tags/<int:tag_id>/rename")
def rename(tag_id):
    # Imported here: notes.py imports this file, so importing it at the top
    # would go round in a circle.
    from .notes import notify

    tag = get_tag_or_404(tag_id)
    name, error = validate_tag_name(request.form)
    if error:
        return index(rename_id=tag_id, rename_value=request.form.get("name", ""), error=error)
    if name == tag["name"]:
        return redirect(url_for("tags.index"))

    db = get_db()
    user_id = g.user["id"]
    existing = db.execute("SELECT id FROM tags WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()
    if not request.form.get("confirm"):
        # Step 1: show what will change, and ask. Step 2 (confirm=1) does it.
        review = {
            "tag": tag, "name": name, "notes": notes_with_tag(db, tag_id),
            "merge_count": len(notes_with_tag(db, existing["id"])) if existing else None,
        }
        return index(rename_id=tag_id, rename_value=name, review=review)

    rewrite_hashtags(db, tag_id, tag["name"], name)
    if existing:
        # Renaming onto a tag that exists merges the two: every note with the
        # old tag gets the other one (OR IGNORE skips notes that had both).
        db.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id)"
                   " SELECT note_id, ? FROM note_tags WHERE tag_id = ?", (existing["id"], tag_id))
        db.execute("DELETE FROM note_tags WHERE tag_id = ?", (tag_id,))
        db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        notify(f"Merged #{tag['name']} into #{name}.")
    else:
        db.execute("UPDATE tags SET name = ? WHERE id = ?", (name, tag_id))
        notify(f"Renamed #{tag['name']} to #{name}.")
    db.commit()
    return redirect(url_for("tags.index"))


@bp.post("/tags/<int:tag_id>/delete")
def delete(tag_id):
    from .notes import notify

    tag = get_tag_or_404(tag_id)
    db = get_db()
    rewrite_hashtags(db, tag_id, tag["name"])
    db.execute("DELETE FROM note_tags WHERE tag_id = ?", (tag_id,))
    db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    db.commit()
    notify(f"Deleted the tag #{tag['name']}. The notes themselves are still there.")
    return redirect(url_for("tags.index"))
