"""The profile page: info, password, theme. And the logo never changes."""
import re

import pytest
from werkzeug.security import check_password_hash

from notes.db import get_db
from notes.validation import THEMES


def test_profile_shows_stats(client, add):
    add("A", body="one two three", pinned=1, tags=["x"])
    add("B", body="four")
    add("Gone", body="not counted", deleted_at="2026-10-19 10:00:00")
    html = client.get("/profile").get_data(as_text=True)
    assert "<strong>2</strong> Notes" in html
    assert "<strong>4</strong> Words written" in html
    assert "<strong>1</strong> Tags" in html
    assert "<strong>1</strong> Pinned" in html


def test_update_info(client, post, query):
    response = post("/profile", {"username": "alice_c", "display_name": "Alice", "avatar": "🌼"})
    assert response.status_code == 302
    user = query("SELECT * FROM users WHERE id = 1")[0]
    assert (user["username"], user["display_name"], user["avatar"]) == ("alice_c", "Alice", "🌼")
    assert "Good morning, Alice" in client.get("/").get_data(as_text=True)


def test_taken_username(post, other_user):
    response = post("/profile", {"username": "BOB"})
    assert response.status_code == 400
    assert "That username is taken" in response.get_data(as_text=True)


def test_change_password(post, query):
    wrong = post("/profile/password", {"current_password": "nope", "new_password": "brand new pw",
                                       "confirm_password": "brand new pw"})
    assert wrong.status_code == 400 and "isn&#39;t your current password" in wrong.get_data(as_text=True)
    post("/profile/password", {"current_password": "correct horse", "new_password": "brand new pw",
                               "confirm_password": "brand new pw"})
    assert check_password_hash(query("SELECT password_hash FROM users WHERE id = 1")[0]["password_hash"], "brand new pw")


def test_save_theme(client, post, query):
    post("/profile/theme", {"theme": "rose", "appearance": "dark"})
    assert query("SELECT theme, appearance FROM users WHERE id = 1")[0] == {"theme": "rose", "appearance": "dark"}
    html = client.get("/").get_data(as_text=True)
    assert '<html lang="en" data-theme="rose"\n      data-appearance="dark">' in html


def test_unknown_theme_is_refused(client, post, query):
    post("/profile/theme", {"theme": "neon", "appearance": "light"})
    assert query("SELECT theme FROM users WHERE id = 1")[0]["theme"] == "default"
    assert "Pick one of the themes." in client.get("/profile").get_data(as_text=True)


@pytest.mark.parametrize("theme", list(THEMES))
@pytest.mark.parametrize("appearance", ["light", "dark"])
def test_logo_and_app_icon_are_the_same_in_every_theme(client, post, theme, appearance):
    """The logo is one fixed image: no theme or dark mode swaps or recolors it."""
    post("/profile/theme", {"theme": theme, "appearance": appearance})
    html = client.get("/").get_data(as_text=True)
    logos = re.findall(r'<img class="brand-logo" src="([^"?]+)', html)
    assert logos and set(logos) == {"/static/logo.png"}
    assert re.search(r'<link rel="icon" type="image/png" href="/static/logo.png\?v=\d+">', html)
    assert re.search(r'<link rel="apple-touch-icon" href="/static/logo.png\?v=\d+">', html)


def test_demo_account_keeps_its_login(app, post, query):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET is_demo = 1 WHERE id = 1")
        db.commit()
    assert post("/profile", {"username": "renamed"}).status_code == 400
    post("/profile/password", {"current_password": "correct horse", "new_password": "brand new pw",
                               "confirm_password": "brand new pw"})
    assert check_password_hash(query("SELECT password_hash FROM users WHERE id = 1")[0]["password_hash"], "correct horse")
