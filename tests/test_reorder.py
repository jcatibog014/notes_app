"""Drag and drop: saving a custom order, pinning by dragging, and the Sort menu."""
from conftest import titles_on


def test_reorder_saves_the_order_and_switches_to_custom(client, fetch_post, add, query):
    a, b, c = add("Alpha"), add("Bravo"), add("Charlie")
    response = fetch_post("/notes/reorder", {"others": [str(c), str(a), str(b)]})
    assert response.json == {"sort": "custom", "label": "Custom order", "saved": 3}
    assert query("SELECT note_sort FROM users WHERE id = 1")[0]["note_sort"] == "custom"
    assert titles_on(client, "/") == ["Charlie", "Alpha", "Bravo"]


def test_dragging_between_sections_pins_and_unpins(client, fetch_post, add, fetch):
    a = add("Alpha", pinned=1)
    b = add("Bravo")
    fetch_post("/notes/reorder", {"pinned": [str(b)], "others": [str(a)]})
    assert fetch(b)["pinned"] == 1 and fetch(a)["pinned"] == 0
    assert titles_on(client, "/") == ["Bravo", "Alpha"]


def test_new_notes_go_first_in_custom_order(client, post, fetch_post, add):
    a, b = add("Alpha"), add("Bravo")
    fetch_post("/notes/reorder", {"others": [str(b), str(a)]})
    post("/notes/new", {"title": "Brand new"})
    assert titles_on(client, "/") == ["Brand new", "Bravo", "Alpha"]


def test_reorder_ignores_other_peoples_and_trashed_notes(fetch_post, add, other_user, fetch):
    mine = add("Mine")
    theirs = add("Theirs", user_id=other_user)
    gone = add("Gone", deleted_at="2026-10-19 10:00:00")
    response = fetch_post("/notes/reorder", {"pinned": [str(theirs), str(gone), str(mine), "nope"]})
    assert response.json["saved"] == 1
    assert fetch(mine)["pinned"] == 1 and fetch(mine)["position"] == 0
    assert fetch(theirs)["position"] is None and fetch(theirs)["pinned"] == 0
    assert fetch(gone)["position"] is None


def test_archived_notes_cant_be_pinned_by_dragging(fetch_post, add, fetch):
    archived = add("Old", archived=1)
    fetch_post("/notes/reorder", {"pinned": [str(archived)]})
    assert fetch(archived)["pinned"] == 0 and fetch(archived)["position"] == 0


def test_a_note_listed_twice_counts_once(fetch_post, add, fetch):
    a = add("Alpha")
    fetch_post("/notes/reorder", {"pinned": [str(a)], "others": [str(a)]})
    assert fetch(a)["pinned"] == 1


def test_reorder_without_javascript_goes_back(post, add):
    a = add("Alpha")
    response = post("/notes/reorder", {"others": [str(a)]})
    assert response.status_code == 302 and response.location.endswith("/")


def test_sort_menu_saves_the_choice(client, post, add, query):
    add("banana")
    add("Apple")
    response = post("/notes/sort", {"sort": "title"})
    assert response.status_code == 302 and response.location.endswith("/")
    assert query("SELECT note_sort FROM users WHERE id = 1")[0]["note_sort"] == "title"
    assert titles_on(client, "/") == ["Apple", "banana"]  # remembered, no ?sort= needed
    assert post("/notes/sort", {"sort": "random"}).status_code == 400


def test_board_can_be_dragged_only_in_plain_lists(client, add):
    add("Note", tags=["work"], pinned=1)
    add("Put away", archived=1)
    add("Thrown out", deleted_at="2026-10-19 10:00:00")
    for url in ["/", "/?view=pinned", "/?view=archive"]:
        assert 'data-reorder-url="/notes/reorder"' in client.get(url).get_data(as_text=True), url
    for url in ["/?q=note", "/?tag=work", "/?view=trash"]:
        assert "data-reorder-url" not in client.get(url).get_data(as_text=True), url


def test_both_sections_are_in_the_page(client, add):
    """An empty section is there (hidden), so app.js can keep its heading in step after a drag."""
    add("Only one, not pinned")
    html = client.get("/").get_data(as_text=True)
    assert '<div class="masonry" data-section="pinned"></div>' in html
    assert 'data-section="others"' in html
    assert 'class="section-label" data-empty>' in html


def test_sidebar_links_are_drop_targets(client, add):
    add("Note", tags=["work"])
    html = client.get("/").get_data(as_text=True)
    assert 'data-drop="pin"' in html and 'data-drop="archive"' in html and 'data-drop="trash"' in html
    assert 'data-drop="tag:work"' in html
    assert 'data-drop="unarchive"' not in html
    archive = client.get("/?view=archive").get_data(as_text=True)
    assert 'data-drop="unarchive"' in archive and 'data-drop="archive"' not in archive


def test_tagging_stays_on_the_same_page(post, add, tags_of):
    """Dropping a card on a tag (or Add Tag in select mode) mustn't jump to that tag's page."""
    note_id = add("Note")
    response = post("/notes/bulk?view=archive", {"action": "tag", "add_tag": "work", "ids": [str(note_id)]})
    assert response.location.endswith("/?view=archive")
    assert tags_of(note_id) == ["work"]


def test_pinning_an_archived_note_brings_it_back(post, add, fetch):
    note_id = add("Old", archived=1)
    post("/notes/bulk", {"action": "pin", "ids": [str(note_id)]})
    assert fetch(note_id)["pinned"] == 1 and fetch(note_id)["archived"] == 0
