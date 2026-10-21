"""validation.py: plain functions, tested without the app."""
from notes.validation import (BODY_MAX, TAGS_MAX, TITLE_MAX, parse_tags, validate_note, validate_profile,
                              validate_registration, validate_settings, validate_tag_name)


def test_a_note_needs_a_title_or_text():
    _, errors = validate_note({"title": "  ", "body": " \n "})
    assert "body" in errors
    assert validate_note({"title": "Only a title"})[1] == {}
    assert validate_note({"body": "Only text"})[1] == {}


def test_note_fields_are_cleaned():
    data, errors = validate_note({"title": "  grocery \n list ", "body": "line\r\nnext\n\n",
                                  "tags": "Home, #errands home", "color": "blue", "pinned": "1"})
    assert errors == {}
    assert data == {"title": "Grocery list", "body": "line\nnext", "tags": ["home", "errands"],
                    "color": "blue", "pinned": 1}


def test_note_limits():
    _, errors = validate_note({"title": "x" * (TITLE_MAX + 1), "body": "y" * (BODY_MAX + 1)})
    assert "title" in errors and "body" in errors
    _, errors = validate_note({"title": "t", "tags": " ".join(f"tag{i}" for i in range(TAGS_MAX + 1))})
    assert "tags" in errors


def test_bad_tags_and_colors():
    assert "tags" in validate_note({"title": "t", "tags": "1st"})[1]          # must start with a letter
    assert "tags" in validate_note({"title": "t", "tags": "a" * 31})[1]
    assert "color" in validate_note({"title": "t", "color": "plaid"})[1]


def test_parse_tags():
    assert parse_tags("a,b  #c, a") == ["a", "b", "c"]
    assert parse_tags("") == []


def test_tag_names():
    assert validate_tag_name({"name": "#Ideas"}) == ("ideas", None)
    assert validate_tag_name({"name": ""})[1]
    assert validate_tag_name({"name": "two words"})[1]


def test_settings():
    assert validate_settings({"theme": "rose", "appearance": "dark"})[1] == {}
    _, errors = validate_settings({"theme": "neon", "appearance": "sideways"})
    assert set(errors) == {"theme", "appearance"}


def test_registration():
    _, errors = validate_registration({"username": "a b", "password": "short", "confirm": "short"})
    assert set(errors) == {"username", "password"}
    _, errors = validate_registration({"username": "ana", "password": "longenough", "confirm": "different"})
    assert set(errors) == {"confirm"}


def test_profile():
    data, errors = validate_profile({"username": "ana", "display_name": "  Ana   Cruz ", "avatar": "🦊"})
    assert errors == {} and data["display_name"] == "Ana Cruz"
    assert "avatar" in validate_profile({"username": "ana", "avatar": "<b>"})[1]
