"""Notes: create, read, update, pin, color, archive, checkboxes, export and import."""
import io

import pytest


def test_home_shows_only_your_notes(client, add, other_user):
    add("Alice's grocery plan")
    add("Bob's secret diary", user_id=other_user)
    html = client.get("/").get_data(as_text=True)
    assert "Alice&#39;s grocery plan" in html
    assert "secret diary" not in html


@pytest.mark.parametrize("method, url", [
    ("get", "/notes/{id}"), ("post", "/notes/{id}"), ("post", "/notes/{id}/pin"),
    ("post", "/notes/{id}/color"), ("post", "/notes/{id}/archive"), ("post", "/notes/{id}/trash"),
    ("post", "/notes/{id}/restore"), ("post", "/notes/{id}/purge"), ("post", "/notes/{id}/check"),
    ("post", "/notes/{id}/duplicate"), ("get", "/notes/{id}/export"),
])
def test_someone_elses_note_is_not_found(client, post, add, other_user, fetch, method, url):
    note_id = add("Bob's note", body="- [ ] private", user_id=other_user)
    url = url.format(id=note_id)
    response = client.get(url) if method == "get" else post(url, {"title": "Hacked", "line": "0", "color": "red"})
    assert response.status_code == 404
    assert fetch(note_id)["title"] == "Bob's note"


def test_create_a_note(client, post, fetch, tags_of, query):
    response = post("/notes/new", {"title": "trip ideas", "body": "Beach #summer\nSee [[Budget]]",
                                   "tags": "travel", "color": "teal", "pinned": "1"})
    assert response.status_code == 302 and response.location.endswith("/notes/1")
    note = fetch(1)
    assert (note["title"], note["color"], note["pinned"]) == ("Trip ideas", "teal", 1)
    assert note["created_at"] == note["updated_at"] == "2026-10-20 09:00:00"
    # Tags come from the tag box and from #tags in the text.
    assert tags_of(1) == ["summer", "travel"]
    assert query("SELECT to_title FROM note_links") == [{"to_title": "budget"}]


def test_an_empty_note_is_refused(post, query):
    response = post("/notes/new", {"title": "", "body": "  "})
    assert response.status_code == 400
    assert "Write something first" in response.get_data(as_text=True)
    assert query("SELECT * FROM notes") == []


def test_quick_capture_stays_on_the_home_page(post, fetch):
    response = post("/notes/new", {"body": "call mom", "next": "index"})
    assert response.status_code == 302 and response.location.endswith("/")
    assert fetch(1)["body"] == "call mom"


def test_autosave_answers_with_json(fetch_post, fetch):
    created = fetch_post("/notes/new", {"title": "Draft", "body": "- [x] one\n- [ ] two"})
    assert created.status_code == 201
    assert created.json["url"] == "/notes/1" and created.json["save_url"] == "/notes/1"
    saved = fetch_post("/notes/1", {"title": "Draft", "body": "three little words"})
    assert saved.status_code == 200
    assert saved.json["words"] == 3 and saved.json["total"] == 0
    assert fetch(1)["body"] == "three little words"
    errors = fetch_post("/notes/1", {"title": "", "body": ""})
    assert errors.status_code == 400 and "body" in errors.json["errors"]


def test_edit_a_note(client, post, add, fetch, tags_of):
    note_id = add("Old title", body="old", tags=["keep"])
    page = client.get(f"/notes/{note_id}").get_data(as_text=True)
    assert 'value="Old title"' in page
    post(f"/notes/{note_id}", {"title": "New title", "body": "new #fresh", "tags": "", "color": "pink"})
    note = fetch(note_id)
    assert (note["title"], note["body"], note["color"]) == ("New title", "new #fresh", "pink")
    assert note["updated_at"] == "2026-10-20 09:00:00"
    assert tags_of(note_id) == ["fresh"]  # "keep" was taken out of the tag box


def test_tag_box_leaves_out_tags_written_in_the_text(client, add):
    note_id = add("Tagged", body="about #cats", tags=["cats", "pets"])
    page = client.get(f"/notes/{note_id}").get_data(as_text=True)
    assert 'name="tags" type="text" value="pets"' in page


def test_editor_shows_errors_and_keeps_input(post, add):
    note_id = add("Fine")
    response = post(f"/notes/{note_id}", {"title": "Keep me", "body": "", "tags": "9lives"})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert 'value="Keep me"' in html and 'id="tags-error"' in html


def test_cards_show_preview_tags_progress_and_time(client, add):
    add("Packing", body="- [x] passport\n- [ ] sunscreen", tags=["travel"])
    html = client.get("/").get_data(as_text=True)
    assert "passport" in html and "#travel" in html
    assert "1/2" in html
    assert "1 h ago" in html


def test_pin_puts_a_note_in_the_pinned_section(client, post, add, fetch):
    note_id = add("Pin me please")
    post(f"/notes/{note_id}/pin")
    assert fetch(note_id)["pinned"] == 1
    html = client.get("/").get_data(as_text=True)
    assert "Pinned</h2>" in html
    post(f"/notes/{note_id}/pin")
    assert fetch(note_id)["pinned"] == 0


def test_change_color(post, add, fetch):
    note_id = add("Colorful")
    post(f"/notes/{note_id}/color", {"color": "yellow"})
    assert fetch(note_id)["color"] == "yellow"
    assert post(f"/notes/{note_id}/color", {"color": "plaid"}).status_code == 400


def test_archive_hides_a_note_from_the_main_list(client, post, add, fetch):
    note_id = add("Old tax stuff", pinned=1)
    post(f"/notes/{note_id}/archive")
    assert fetch(note_id)["archived"] == 1 and fetch(note_id)["pinned"] == 0
    # (The "Archived …" toast names it too, so look for its card's title.)
    assert "Old tax stuff</h3>" not in client.get("/").get_data(as_text=True)
    assert "Old tax stuff</h3>" in client.get("/?view=archive").get_data(as_text=True)
    post(f"/notes/{note_id}/archive")
    assert fetch(note_id)["archived"] == 0


def test_actions_go_back_to_the_same_view(post, add):
    note_id = add("Somewhere", archived=1)
    response = post(f"/notes/{note_id}/pin?view=archive&q=some")
    assert response.location.endswith("/?view=archive&q=some")
    response = post(f"/notes/{note_id}/pin", {"next": "editor"})
    assert response.location.endswith(f"/notes/{note_id}")


def test_tick_a_checkbox(post, fetch_post, add, fetch):
    note_id = add("List", body="List\n- [ ] eggs\n- [ ] milk")
    response = fetch_post(f"/notes/{note_id}/check", {"line": "2"})
    assert response.json == {"done": 1, "total": 2}
    assert fetch(note_id)["body"] == "List\n- [ ] eggs\n- [x] milk"
    assert post(f"/notes/{note_id}/check", {"line": "0"}).status_code == 400
    assert post(f"/notes/{note_id}/check", {"line": "abc"}).status_code == 400


def test_preview_renders_safely(post):
    response = post("/preview", {"body": "**hi** <img src=x onerror=alert(1)>"})
    html = response.get_data(as_text=True)
    assert "<strong>hi</strong>" in html and "<img" not in html


def test_duplicate(post, add, fetch, tags_of):
    note_id = add("Template", body="text", tags=["work"], color="green")
    response = post(f"/notes/{note_id}/duplicate")
    copy_id = int(response.location.rsplit("/", 1)[1])
    copy = fetch(copy_id)
    assert (copy["title"], copy["body"], copy["color"]) == ("Template (copy)", "text", "green")
    assert tags_of(copy_id) == ["work"]


def test_export_as_markdown(client, add):
    note_id = add("Trip: Day 1!", body="- [ ] pack", tags=["travel"])
    response = client.get(f"/notes/{note_id}/export")
    assert response.headers["Content-Disposition"] == 'attachment; filename="trip-day-1.md"'
    assert response.get_data(as_text=True) == "---\ntitle: Trip: Day 1!\ntags: travel\n---\n\n- [ ] pack\n"


def test_import_markdown_files(post, query, tags_of):
    files = [
        (io.BytesIO(b"---\ntitle: Imported\ntags: [old, notes]\n---\n\nHello #there"), "a.md"),
        (io.BytesIO(b"# From heading\nbody"), "b.markdown"),
        (io.BytesIO(b"\x89PNG"), "picture.png"),
    ]
    response = post("/notes/import", {"files": files}, content_type="multipart/form-data")
    assert response.status_code == 302
    rows = query("SELECT id, title, body FROM notes ORDER BY id")
    assert [(row["title"], row["body"]) for row in rows] == [("Imported", "Hello #there"), ("From heading", "body")]
    assert tags_of(rows[0]["id"]) == ["notes", "old", "there"]
