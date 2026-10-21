"""The home page's helpers: sort, filter chips, Jump Back In, templates,
select mode (bulk actions), Export All, and the welcome tour."""
import io
import json
import re
import zipfile

from conftest import titles_on


def test_sort_by_title_and_created(client, add):
    add("banana", created_at="2026-10-01 10:00:00", updated_at="2026-10-19 10:00:00")
    add("Apple", created_at="2026-10-05 10:00:00", updated_at="2026-10-02 10:00:00")
    add("cherry", created_at="2026-10-03 10:00:00", updated_at="2026-10-20 08:00:00")
    assert titles_on(client, "/") == ["cherry", "banana", "Apple"]
    assert titles_on(client, "/?sort=title") == ["Apple", "banana", "cherry"]
    assert titles_on(client, "/?sort=created") == ["Apple", "cherry", "banana"]
    assert titles_on(client, "/?sort=nonsense") == ["cherry", "banana", "Apple"]


def test_pinned_notes_stay_on_top_whatever_the_sort(client, add):
    add("Zebra", pinned=1)
    add("Aardvark")
    assert titles_on(client, "/?sort=title") == ["Zebra", "Aardvark"]


def test_filter_chips_switch_filters_on_and_off(client, add):
    add("Note", tags=["work"])
    html = client.get("/").get_data(as_text=True)
    assert 'href="/?q=is:pinned"' in html
    assert 'href="/?q=has:checklist"' in html
    assert 'href="/?q=color:blue"' in html
    assert 'href="/?q=tag:work"' in html
    # When on, the chip's link takes the filter back out.
    html = client.get("/?q=budget+is:pinned").get_data(as_text=True)
    assert 'class="chip chip-toggle is-on" href="/?q=budget"' in html


def test_did_you_mean(client):
    html = client.get("/?q=tags:work").get_data(as_text=True)
    assert "“tags:work” isn't a filter." in html
    assert '<a href="/?q=tag:work"><code>tag:work</code></a>' in html
    html = client.get("/?q=is:pin").get_data(as_text=True)
    assert "<code>is:pinned</code>" in html
    assert "isn't a filter" not in client.get("/?q=10:30").get_data(as_text=True)


def test_jump_back_in_lists_recently_opened_notes(client, add):
    first = add("Opened first")
    second = add("Opened second")
    add("Never opened")
    assert "Jump Back In" not in client.get("/").get_data(as_text=True)
    client.get(f"/notes/{first}")
    client.get(f"/notes/{second}")
    html = client.get("/").get_data(as_text=True)
    section = html.split("Jump Back In")[1].split("</nav>")[0]
    assert ">Opened second</a>" in section and ">Opened first</a>" in section
    assert "Never opened" not in section


def test_opening_a_note_doesnt_count_as_editing(client, add, fetch):
    note_id = add("Just looking")
    client.get(f"/notes/{note_id}")
    assert fetch(note_id)["updated_at"] == "2026-10-20 08:00:00"
    assert fetch(note_id)["opened_at"] == "2026-10-20 09:00:00"


def test_templates(client):
    html = client.get("/notes/new?template=checklist").get_data(as_text=True)
    assert "- [ ] \n- [ ] \n- [ ] </textarea>" in html
    html = client.get("/notes/new?template=journal").get_data(as_text=True)
    assert 'value="Tuesday, October 20"' in html
    assert client.get("/notes/new?template=nope").status_code == 200


def test_bulk_pin_archive_and_tag(post, add, fetch, tags_of):
    a = add("A")
    b = add("B", tags=["old"])
    post("/notes/bulk", {"action": "pin", "ids": [str(a), str(b)]})
    assert fetch(a)["pinned"] == fetch(b)["pinned"] == 1
    post("/notes/bulk", {"action": "tag", "tag": "#Work", "ids": [str(a), str(b)]})
    assert tags_of(a) == ["work"] and tags_of(b) == ["old", "work"]
    post("/notes/bulk", {"action": "archive", "ids": [str(a)]})
    assert fetch(a)["archived"] == 1 and fetch(a)["pinned"] == 0


def test_bulk_trash_offers_undo_for_all(client, post, add, fetch):
    a = add("A")
    b = add("B")
    post("/notes/bulk", {"action": "trash", "ids": [str(a), str(b)]})
    assert fetch(a)["deleted_at"] and fetch(b)["deleted_at"]
    html = client.get("/").get_data(as_text=True)
    assert "Moved 2 notes to the Trash." in html
    assert f'name="ids" value="{a}"' in html and f'name="ids" value="{b}"' in html


def test_bulk_ignores_other_peoples_notes(post, add, other_user, fetch):
    mine = add("Mine")
    theirs = add("Theirs", user_id=other_user)
    post("/notes/bulk", {"action": "trash", "ids": [str(mine), str(theirs), "abc"]})
    assert fetch(mine)["deleted_at"] and fetch(theirs)["deleted_at"] is None


def test_bulk_needs_notes_and_an_action(client, post, add):
    note_id = add("A")
    post("/notes/bulk", {"action": "pin"})
    assert "Select some notes first." in client.get("/").get_data(as_text=True)
    assert post("/notes/bulk", {"action": "explode", "ids": [str(note_id)]}).status_code == 400
    post("/notes/bulk", {"action": "tag", "tag": "", "ids": [str(note_id)]})
    assert "Type a tag to add" in client.get("/").get_data(as_text=True)


def test_export_all_as_zip(client, add, other_user):
    add("Ideas", body="one", tags=["x"])
    add("Ideas", body="two")
    add("Gone", body="trashed", deleted_at="2026-10-19 10:00:00")
    add("Bob's", user_id=other_user)
    response = client.get("/notes/export.zip")
    assert response.headers["Content-Disposition"] == 'attachment; filename="forget-me-note.zip"'
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert sorted(archive.namelist()) == ["ideas-2.md", "ideas.md"]
        assert archive.read("ideas.md").decode() == "---\ntitle: Ideas\ntags: x\n---\n\none\n"


def test_copy_as_plain_text(post):
    response = post("/plain", {"body": "# Title\n- [x] **done**"})
    assert response.get_data(as_text=True) == "Title\ndone"


def test_welcome_tour_shows_until_done(client, post, query):
    assert 'id="tour"' in client.get("/").get_data(as_text=True)
    post("/welcome/done")
    assert query("SELECT onboarded FROM users WHERE id = 1")[0]["onboarded"] == 1
    assert 'id="tour"' not in client.get("/").get_data(as_text=True)
    post("/welcome/again")
    assert 'id="tour"' in client.get("/").get_data(as_text=True)


def test_empty_home_teaches(client, post):
    post("/welcome/done")
    html = client.get("/").get_data(as_text=True)
    assert "Type <code>#work</code> in a note to tag it." in html
    assert "<code>[[Another note]]</code>" in html


def test_archive_and_trash_link_to_each_other(client):
    html = client.get("/?view=archive").get_data(as_text=True)
    assert 'href="/?view=trash"' in html
    assert '<details class="side-more" open>' in html
    assert '<details class="side-more" >' in client.get("/").get_data(as_text=True)


def test_editor_data_is_safe_inside_its_script_tag(client, add):
    add("</script><script>alert(1)</script>")
    add("Current")
    html = client.get("/notes/2").get_data(as_text=True)
    data = re.search(r'<script type="application/json" id="editor-data">(.*?)</script>', html).group(1)
    assert "</script>" not in data and "<script>" not in data
    assert json.loads(data)["titles"] == ["</script><script>alert(1)</script>"]


def test_editor_marks_tags_from_the_text(client, add):
    note_id = add("Tagged", body="about #cats and #dogs", tags=["cats", "dogs", "pets"])
    html = client.get(f"/notes/{note_id}").get_data(as_text=True)
    assert 'value="pets"' in html
    assert 'data-text-tags="cats,dogs"' in html
