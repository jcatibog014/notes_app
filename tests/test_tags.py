"""Tags: the sidebar, the tag manager, rename, merge and delete."""


def test_sidebar_lists_tags_with_counts(client, add):
    add("One", tags=["work", "ideas"])
    add("Two", tags=["work"])
    add("Gone", tags=["old"], deleted_at="2026-10-19 10:00:00")
    html = client.get("/").get_data(as_text=True)
    assert '<span class="side-tag-name">work</span><span class="count">2</span>' in html
    assert '<span class="side-tag-name">ideas</span><span class="count">1</span>' in html
    assert '<span class="side-tag-name">old</span>' not in html  # only notes in the Trash have it


def test_unused_tags_are_removed_on_save(post, add, query):
    note_id = add("Note", tags=["temporary"])
    post(f"/notes/{note_id}", {"title": "Note", "tags": "lasting"})
    assert [row["name"] for row in query("SELECT name FROM tags")] == ["lasting"]


def test_rename_shows_the_affected_notes_first(post, add, fetch, tags_of):
    note_id = add("Thesis outline", body="about #idea", tags=["idea"])
    response = post("/tags/1/rename", {"name": "plan"})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Rename #idea to <strong>#plan</strong>?" in html
    assert f'<a href="/notes/{note_id}">Thesis outline</a>' in html
    assert 'name="confirm" value="1"' in html
    # Nothing changed yet.
    assert tags_of(note_id) == ["idea"] and fetch(note_id)["body"] == "about #idea"


def test_rename_also_changes_hashtags_in_the_text(post, add, fetch, tags_of):
    note_id = add("Note", body="about #Idea and #ideas", tags=["idea", "ideas"])
    post("/tags/1/rename", {"name": "plan", "confirm": "1"})
    assert fetch(note_id)["body"] == "about #plan and #ideas"
    assert tags_of(note_id) == ["ideas", "plan"]


def test_merging_warns_before_it_happens(post, add, tags_of):
    first = add("First", tags=["todo"])
    add("Second", tags=["tasks"])
    html = post("/tags/1/rename", {"name": "tasks"}).get_data(as_text=True)
    assert "This merges two tags." in html
    assert "You already have #tasks (1 note)" in html
    assert "Merge Tags" in html
    assert tags_of(first) == ["todo"]


def test_rename_onto_an_existing_tag_merges(client, post, add, tags_of, query):
    first = add("First", tags=["todo"])
    second = add("Second", tags=["todo", "tasks"])
    response = post("/tags/1/rename", {"name": "tasks", "confirm": "1"})  # tag 1 is "todo"
    assert response.status_code == 302
    assert tags_of(first) == ["tasks"] and tags_of(second) == ["tasks"]
    assert [row["name"] for row in query("SELECT name FROM tags")] == ["tasks"]
    assert "Merged #todo into #tasks." in client.get("/tags").get_data(as_text=True)


def test_bad_rename_shows_the_error(post, add):
    add("Note", tags=["fine"])
    response = post("/tags/1/rename", {"name": "two words"})
    assert response.status_code == 400
    assert "A tag is one word" in response.get_data(as_text=True)


def test_delete_a_tag_keeps_the_notes(post, add, fetch, tags_of):
    note_id = add("Kept", body="loving #cats", tags=["cats", "pets"])
    post("/tags/1/delete")
    assert fetch(note_id)["body"] == "loving cats"
    assert tags_of(note_id) == ["pets"]


def test_someone_elses_tag_is_not_found(post, add, other_user):
    add("Bob's", tags=["private"], user_id=other_user)
    assert post("/tags/1/rename", {"name": "mine"}).status_code == 404
    assert post("/tags/1/delete").status_code == 404
