"""Accounts: sign up, log in, log out, and pages that need a login."""
from conftest import CSRF, PASSWORD, USERNAME


def test_logged_out_visitors_go_to_login(guest):
    for url in ["/", "/notes/new", "/tags", "/profile"]:
        response = guest.get(url)
        assert response.status_code == 302 and response.location.endswith("/login")


def test_register_logs_you_in(guest, post):
    response = post("/register", {"username": "carla", "password": "longenough", "confirm": "longenough"})
    assert response.status_code == 302
    assert "Welcome, carla" in guest.get("/").get_data(as_text=True)


def test_register_refuses_a_taken_name(guest, post):
    response = post("/register", {"username": "Alice", "password": "longenough", "confirm": "longenough"})
    assert response.status_code == 400
    assert "That username is taken" in response.get_data(as_text=True)


def test_login(guest, post):
    bad = post("/login", {"username": USERNAME, "password": "wrong"})
    assert bad.status_code == 400 and "Incorrect username or password" in bad.get_data(as_text=True)
    good = post("/login", {"username": USERNAME, "password": PASSWORD})
    assert good.status_code == 302


def test_logout(client, post):
    post("/logout")
    assert client.get("/").status_code == 302


def test_post_without_csrf_token_is_refused(client):
    response = client.post("/notes/new", data={"title": "Sneaky"})
    assert response.status_code == 400
    response = client.post("/notes/new", data={"title": "Sneaky", "csrf_token": CSRF + "x"})
    assert response.status_code == 400
