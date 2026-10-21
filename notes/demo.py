"""One demo account, full of example notes, to show the app to someone.

Make it on the server with:

    flask --app notes create-demo

It asks for a username and a password, so the password never has to be
written in the code (which is public on GitHub). Running it again puts
fresh example notes back. The account is marked users.is_demo = 1, and
the profile page won't let anyone change its username or password, so the
login you share keeps working.
"""
from datetime import timedelta

import click
from flask import current_app, g
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .db import get_db
from .notes import delete_notes, insert_note, timestamp
from .validation import password_error, username_error

# The example notes. "hours" is how long ago each was written; the other
# keys are the editor's fields.
DEMO_NOTES = [
    {"title": "Welcome to Forget-Me-Note 🌼", "color": "blue", "pinned": 1, "hours": 0,
     "body": "Your notes, neatly kept. A few things to try:\n\n"
             "- [x] Open this note\n- [ ] Tick a box right on the card\n"
             "- [ ] Search with **Ctrl+K**, like `tag:ideas` or `\"exact words\"`\n"
             "- [ ] Write a `#tag` anywhere in the text\n- [ ] Link notes with [[Trip to Siargao]]\n\n"
             "Formatting is **Markdown**: *italic*, ~~struck~~, `code`, > quotes and more."},
    {"title": "Trip to Siargao", "color": "teal", "pinned": 1, "hours": 5, "tags": ["travel"],
     "body": "## Packing\n- [x] Passport\n- [x] Sunscreen\n- [ ] Rash guard\n- [ ] Dry bag\n\n"
             "## Spots\n1. Cloud 9 boardwalk\n2. Magpupungko rock pools\n3. Sugba lagoon\n\n"
             "Budget is in [[Monthly budget]]."},
    {"title": "Monthly budget", "color": "green", "hours": 26, "tags": ["money"],
     "body": "- Rent: ₱12,000\n- Food: ₱6,000\n- Transport: ₱2,000\n- Savings: **20%** first, always\n\n"
             "> Pay yourself first. #habits"},
    {"title": "Thesis ideas", "color": "purple", "hours": 50, "tags": ["school", "ideas"],
     "body": "Questions worth asking:\n\n- Can small *daily* notes beat long weekly reviews?\n"
             "- How do people actually search their notes?\n\nRead: https://en.wikipedia.org/wiki/Zettelkasten"},
    {"title": "Adobo (Lola's way)", "color": "orange", "hours": 80, "tags": ["recipes"],
     "body": "1. Brown 1 kg chicken\n2. Add ½ cup vinegar, ⅓ cup soy sauce, garlic, bay leaves, peppercorns\n"
             "3. **Don't stir** until the vinegar boils\n4. Simmer 30 min\n\n#family"},
    {"title": "Standup notes", "color": "yellow", "hours": 120, "tags": ["work"],
     "body": "- Shipped search snippets\n- Next: tag manager\n- ~~Blocked on API keys~~ fixed\n\n"
             "```\nflask --app notes run --debug\n```"},
    {"title": "", "color": "pink", "hours": 200,
     "body": "Remember: the best notes app is the one you actually open. 🌸"},
    {"title": "Books to read", "hours": 400, "tags": ["ideas"],
     "body": "- [ ] *Atomic Habits*\n- [x] *Deep Work*\n- [ ] *How to Take Smart Notes*"},
]


@click.command("create-demo")
@click.option("--username", prompt="Demo username", default="demo", show_default=True)
# hide_input keeps the password off the screen, and confirmation_prompt asks twice.
@click.option("--password", prompt="Demo password", hide_input=True, confirmation_prompt=True)
@with_appcontext  # gives the command the app's config and database, like a page has
def create_demo_command(username, password):
    """Make the demo account (or refill it) with example notes."""
    username = username.strip()
    if error := username_error(username) or password_error(password):
        raise click.UsageError(error)

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user and not user["is_demo"]:
        # Plain quotes: some consoles can't show curly ones.
        raise click.UsageError(f'"{username}" is a real person\'s account. Pick another username for the demo.')

    if user:
        # Run again: same account, new password.
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), user["id"]))
        user_id = user["id"]
    else:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, display_name, avatar, is_demo)"
            " VALUES (?, ?, 'Demo', '🌼', 1)",
            (username, generate_password_hash(password)),
        )
        user_id = cursor.lastrowid
    db.commit()

    # insert_note() and delete_notes() work on g.user, like they do on a page.
    g.user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    delete_notes("1 = 1", [])  # all of the demo's notes, for a fresh start
    now = current_app.config["NOW"]()
    # Oldest first, so the [[links]] and the order on the page come out right.
    for example in reversed(DEMO_NOTES):
        data = {"title": example["title"], "body": example["body"], "tags": example.get("tags", []),
                "color": example.get("color", "default"), "pinned": example.get("pinned", 0)}
        insert_note(data, created_at=timestamp(now - timedelta(hours=example["hours"])))
    click.echo(f'Demo account ready. Log in as "{username}" with the password you typed.')


def init_app(app):
    app.cli.add_command(create_demo_command)
