"""The profile page: your picture, name, username, password and theme.

A theme only changes the accent colors (see style.css). The logo and app
icon are one fixed image, static/logo.png, the same in every theme.
"""
import sqlite3

from flask import Blueprint, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import require_login
from .db import get_db
from .markdown import word_count
from .notes import notify
from .validation import (
    APPEARANCES,
    AVATAR_CHOICES,
    DISPLAY_NAME_MAX,
    EDITOR_MODES,
    PASSWORD_MIN,
    THEMES,
    USERNAME_MAX,
    validate_password_change,
    validate_profile,
    validate_settings,
)

bp = Blueprint("profile", __name__)
bp.before_request(require_login)


def profile_stats():
    """The numbers in the profile's header."""
    db = get_db()
    notes = db.execute(
        "SELECT body, pinned FROM notes WHERE user_id = ? AND deleted_at IS NULL", (g.user["id"],)
    ).fetchall()
    tags = db.execute(
        "SELECT COUNT(DISTINCT note_tags.tag_id) FROM note_tags JOIN notes ON notes.id = note_tags.note_id"
        " WHERE notes.user_id = ? AND notes.deleted_at IS NULL",
        (g.user["id"],),
    ).fetchone()[0]
    return {
        "notes": len(notes),
        "words": sum(word_count(note["body"]) for note in notes),
        "tags": tags,
        "pinned": sum(note["pinned"] for note in notes),
    }


def render_profile(info_form=None, info_errors=None, password_errors=None):
    """The profile page. With errors, it answers 400 and keeps what was typed.

    The page has three separate forms, so each one gets its own errors.
    Passwords are never sent back to the browser.
    """
    info_form = info_form or {
        "username": g.user["username"],
        "display_name": g.user["display_name"] or "",
        "avatar": g.user["avatar"] or "",
    }
    html = render_template(
        "profile.html", info_form=info_form, info_errors=info_errors or {},
        password_errors=password_errors or {}, stats=profile_stats(),
        themes=THEMES, appearances=APPEARANCES, avatar_choices=AVATAR_CHOICES,
        username_max=USERNAME_MAX, display_name_max=DISPLAY_NAME_MAX, password_min=PASSWORD_MIN,
        member_since=g.user["created_at"][:10],
    )
    return html, 400 if info_errors or password_errors else 200


@bp.get("/profile")
def index():
    return render_profile()


@bp.post("/profile")
def update_info():
    data, errors = validate_profile(request.form)
    # The demo login is shared (see demo.py), so its username must stay put.
    # The box is read-only on the page, but a form can be sent without it.
    if g.user["is_demo"] and data["username"] != g.user["username"]:
        errors["username"] = "The demo account's username can't be changed."
    if not errors:
        db = get_db()
        try:
            db.execute(
                "UPDATE users SET username = ?, display_name = ?, avatar = ? WHERE id = ?",
                (data["username"], data["display_name"], data["avatar"], g.user["id"]),
            )
            db.commit()
        except sqlite3.IntegrityError:
            # The UNIQUE rule on users.username: someone else has that name.
            errors["username"] = "That username is taken. Try another one."
    if errors:
        return render_profile(info_form=request.form, info_errors=errors)
    notify("Saved your profile.")
    return redirect(url_for("profile.index"))


@bp.post("/profile/password")
def change_password():
    if g.user["is_demo"]:
        # The demo password is set with "flask create-demo" (demo.py), so the
        # people it's shared with can't lock each other out.
        notify("The demo account's password can't be changed here.", "error")
        return redirect(url_for("profile.index"))
    new_password, errors = validate_password_change(request.form)
    # Asking for the current password stops someone who finds your phone
    # unlocked from locking you out of your own account.
    current = request.form.get("current_password", "")
    if current and not check_password_hash(g.user["password_hash"], current):
        errors["current_password"] = "That isn't your current password."
    if errors:
        return render_profile(password_errors=errors)
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(new_password), g.user["id"]))
    db.commit()
    notify("Changed your password. Use the new one next time you log in.")
    return redirect(url_for("profile.index"))


@bp.post("/profile/preferences")
def change_preferences():
    # A ticked checkbox sends its value. An unticked one sends nothing.
    show_greeting = 1 if request.form.get("show_greeting") else 0
    db = get_db()
    db.execute("UPDATE users SET show_greeting = ? WHERE id = ?", (show_greeting, g.user["id"]))
    db.commit()
    notify("Saved your preferences.")
    return redirect(url_for("profile.index") + "#preferences")


@bp.post("/profile/editor-mode")
def change_editor_mode():
    """The editor remembers Write, Split or Preview for this account (sent by app.js)."""
    mode = request.form.get("mode", "")
    if mode not in EDITOR_MODES:
        return "", 400
    db = get_db()
    db.execute("UPDATE users SET editor_mode = ? WHERE id = ?", (mode, g.user["id"]))
    db.commit()
    return "", 204


@bp.post("/profile/theme")
def change_theme():
    data, errors = validate_settings(request.form)
    if errors:
        for message in errors.values():
            notify(message, "error")
    else:
        db = get_db()
        db.execute("UPDATE users SET theme = ?, appearance = ? WHERE id = ?",
                   (data["theme"], data["appearance"], g.user["id"]))
        db.commit()
        notify(f"Theme saved: {THEMES[data['theme']]}, {APPEARANCES[data['appearance']].lower()}.")
    return redirect(url_for("profile.index") + "#theme")
