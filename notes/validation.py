"""Checking what the user typed into the note, sign-up and profile forms.

These are plain functions: form data goes in, and clean data plus error
messages come out. They don't use Flask or the database, which makes them
easy to test (see tests/test_validation.py).
"""
import re

TITLE_MAX = 120
BODY_MAX = 50_000  # about 25 pages of text
TAG_LENGTH_MAX = 30
# Letters (any language), digits, - and _. A tag must start with a letter,
# so "#1" in a list like "step #1" isn't taken for a tag.
TAG_FORMAT = re.compile(rf"[^\W\d_][\w-]{{0,{TAG_LENGTH_MAX - 1}}}")
TAGS_MAX = 15

# The colors a note can have. style.css has a .note-<name> class for each.
# They are fixed pastels, the same in every theme.
NOTE_COLORS = {
    "default": "No color",
    "red": "Red",
    "orange": "Orange",
    "yellow": "Yellow",
    "green": "Green",
    "teal": "Teal",
    "blue": "Blue",
    "purple": "Purple",
    "pink": "Pink",
}

# Color themes, named after flowers. A theme changes only the accent colors:
# the logo and the note colors stay the same in all of them.
THEMES = {
    "default": "Forget-Me-Not",  # periwinkle blue, from the logo
    "lavender": "Lavender",
    "rose": "Rose",
    "mint": "Mint",
    "marigold": "Marigold",
    "ink": "Ink",
}
APPEARANCES = {"system": "Match my device", "light": "Light", "dark": "Dark"}
# The editor's views. The last one used is saved per user (users.editor_mode).
EDITOR_MODES = ["write", "split", "preview"]
# How the home page can sort notes: key -> (label, SQL ORDER BY). The SQL is
# fixed here, never taken from the user.
SORTS = {
    "updated": ("Last edited", "notes.updated_at DESC, notes.id DESC"),
    "created": ("Date created", "notes.created_at DESC, notes.id DESC"),
    "title": ("Title", "notes.title = '', notes.title COLLATE NOCASE, notes.id"),
}

# The profile picture choices. Nobody uploads a photo: an emoji is enough.
AVATAR_CHOICES = ["😀", "😎", "🦊", "🐱", "🐼", "🐸", "🌸", "🌼",
                  "🌈", "⚡", "🍀", "🎧", "🚀", "🧋", "🎨", "📚"]
# An emoji is a few characters that aren't letters, digits, spaces or HTML symbols.
EMOJI_FORMAT = re.compile(r"[^\w\s<>&\"']{1,8}")
DISPLAY_NAME_MAX = 40

USERNAME_MIN = 3
USERNAME_MAX = 30
USERNAME_FORMAT = re.compile(rf"[A-Za-z0-9_]{{{USERNAME_MIN},{USERNAME_MAX}}}")
PASSWORD_MIN = 8


def capitalize_first(text):
    """Start the text with a capital letter: "grocery list" -> "Grocery list".

    Only the first letter changes. A first word that mixes cases on purpose,
    like "iPhone" or "eBay", is left alone, and so is everything after it.
    """
    if not text or not text[0].islower():
        return text
    rest_of_word = text.split()[0][1:]
    if rest_of_word != rest_of_word.lower():  # "iPhone": "Phone" has a capital
        return text
    return text[0].upper() + text[1:]


def parse_tags(text):
    """Split "home, Errands #ideas" into ["home", "errands", "ideas"].

    Tags can be separated by commas or spaces, and may start with #. They're
    lowercased, and repeats are dropped (keeping the first one's place).
    """
    tags = []
    for word in re.split(r"[\s,]+", text):
        tag = word.lstrip("#").lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def tags_error(tags):
    """The problem with a list of tags, or None. Shared by notes and the tag manager."""
    if any(not TAG_FORMAT.fullmatch(tag) for tag in tags):
        return (f"Tags start with a letter and use letters, numbers, - and _,"
                f" up to {TAG_LENGTH_MAX} characters each.")
    if len(tags) > TAGS_MAX:
        return f"Use {TAGS_MAX} tags or fewer."
    return None


def validate_note(form):
    """Return (data, errors) for the note editor.

    The fields are title, body, tags (typed like "home, ideas"), color (one
    of NOTE_COLORS) and pinned (a checkbox). A note needs a title or some
    text, but not both: a quick thought doesn't need a name.

    `data` holds the cleaned values, ready to save.
    `errors` maps a field name to a message. The form is valid when it's empty.
    """
    errors = {}
    # Trim spaces first, so a title of "   " counts as empty. Titles are one
    # line: squash any newlines or runs of spaces a paste brought along.
    title = capitalize_first(" ".join(form.get("title", "").split()))
    # The body keeps its spaces (indentation matters in lists and code), but
    # Windows line endings become plain "\n" and blank lines at the end go.
    body = form.get("body", "").replace("\r\n", "\n").rstrip()
    tags = parse_tags(form.get("tags", ""))
    color = form.get("color") or "default"

    if not title and not body.strip():
        errors["body"] = "Write something first: a title or some text."
    if len(title) > TITLE_MAX:
        errors["title"] = f"Title must be {TITLE_MAX} characters or fewer (it has {len(title)})."
    if len(body) > BODY_MAX:
        errors["body"] = f"Notes can be up to {BODY_MAX:,} characters (this one has {len(body):,})."
    if error := tags_error(tags):
        errors["tags"] = error
    if color not in NOTE_COLORS:
        errors["color"] = "Pick one of the colors."

    data = {
        "title": title,
        "body": body,
        "tags": tags,
        "color": color,
        # A ticked checkbox sends its value. An unticked one sends nothing.
        "pinned": 1 if form.get("pinned") else 0,
    }
    return data, errors


def validate_tag_name(form):
    """Return (name, error) for renaming a tag in the tag manager."""
    tags = parse_tags(form.get("name", ""))
    if not tags:
        return "", "Type the new name."
    if len(tags) > 1:
        return tags[0], "A tag is one word: use - or _ instead of spaces."
    return tags[0], tags_error(tags)


def validate_settings(form):
    """Return (data, errors) for the theme and appearance settings."""
    errors = {}
    theme = form.get("theme", "")
    appearance = form.get("appearance", "")
    if theme not in THEMES:
        errors["theme"] = "Pick one of the themes."
    if appearance not in APPEARANCES:
        errors["appearance"] = "Pick light, dark or match my device."
    return {"theme": theme, "appearance": appearance}, errors


def validate_registration(form):
    """Return (data, errors) for the sign-up form, like validate_note().

    Whether the username is already taken needs the database, so auth.py
    checks that part.
    """
    errors = {}

    username = form.get("username", "").strip()
    # Passwords are not trimmed: a space can be part of a password.
    password = form.get("password", "")
    confirm = form.get("confirm", "")

    # The walrus operator := saves the result and checks it in one step.
    if error := username_error(username):
        errors["username"] = error
    if error := password_error(password):
        errors["password"] = error
    elif password != confirm:
        errors["confirm"] = "The passwords don't match."

    return {"username": username, "password": password}, errors


def username_error(username):
    """The problem with a username, or None. Shared by sign-up and the profile."""
    if not username:
        return "Username is required."
    if not USERNAME_FORMAT.fullmatch(username):
        return f"Use {USERNAME_MIN} to {USERNAME_MAX} letters, numbers or underscores (_)."
    return None


def password_error(password):
    if len(password) < PASSWORD_MIN:
        return f"Password must be at least {PASSWORD_MIN} characters."
    return None


def validate_profile(form):
    """Return (data, errors) for the "Your info" form on the profile page.

    Whether the new username is taken needs the database, so profile.py
    checks that part.
    """
    errors = {}
    username = form.get("username", "").strip()
    display_name = " ".join(form.get("display_name", "").split()) or None  # squash extra spaces
    avatar = form.get("avatar", "").strip() or None

    if error := username_error(username):
        errors["username"] = error
    if display_name and len(display_name) > DISPLAY_NAME_MAX:
        errors["display_name"] = f"Your name must be {DISPLAY_NAME_MAX} characters or fewer."
    if avatar and not EMOJI_FORMAT.fullmatch(avatar):
        errors["avatar"] = "Pick one of the pictures."
    return {"username": username, "display_name": display_name, "avatar": avatar}, errors


def validate_password_change(form):
    """Return (new_password, errors) for the "Change password" form.

    Whether the current password is right needs the saved hash, so
    profile.py checks that part.
    """
    errors = {}
    new = form.get("new_password", "")
    if not form.get("current_password"):
        errors["current_password"] = "Type your current password."
    if error := password_error(new):
        errors["new_password"] = error
    elif new != form.get("confirm_password", ""):
        errors["confirm_password"] = "The new passwords don't match."
    return new, errors
