"""The Trash: soft delete, Undo, restore, delete forever, and the 30-day clean-up."""


def test_trash_hides_a_note_and_offers_undo(client, post, add, fetch):
    note_id = add("Throw me away", pinned=1)
    response = post(f"/notes/{note_id}/trash")
    assert response.status_code == 302
    note = fetch(note_id)
    assert note["deleted_at"] == "2026-10-20 09:00:00" and note["pinned"] == 0
    html = client.get("/").get_data(as_text=True)
    assert "Moved “Throw me away” to the Trash." in html
    assert f'action="/notes/{note_id}/restore"' in html  # the Undo button
    assert "Throw me away</h3>" not in html
    assert "Throw me away" in client.get("/?view=trash").get_data(as_text=True)


def test_restore(post, add, fetch):
    note_id = add("Comeback", deleted_at="2026-10-19 10:00:00")
    post(f"/notes/{note_id}/restore")
    assert fetch(note_id)["deleted_at"] is None


def test_a_note_in_the_trash_cant_be_edited(client, post, add, fetch):
    note_id = add("Frozen", body="- [ ] x", deleted_at="2026-10-19 10:00:00")
    assert post(f"/notes/{note_id}", {"title": "Changed"}).status_code == 400
    assert post(f"/notes/{note_id}/check", {"line": "0"}).status_code == 400
    assert fetch(note_id)["title"] == "Frozen"
    assert "Restore it to edit it" in client.get(f"/notes/{note_id}").get_data(as_text=True)


def test_delete_forever_only_from_the_trash(post, add, fetch, query):
    note_id = add("Not yet", tags=["solo"])
    assert post(f"/notes/{note_id}/purge").status_code == 400
    post(f"/notes/{note_id}/trash")
    post(f"/notes/{note_id}/purge")
    assert fetch(note_id) is None
    # Its tag links went too, and the tag no note uses any more.
    assert query("SELECT * FROM note_tags") == []
    assert query("SELECT * FROM tags") == []


def test_empty_trash(post, add, fetch):
    gone = add("Gone", deleted_at="2026-10-19 10:00:00")
    kept = add("Kept")
    post("/trash/empty")
    assert fetch(gone) is None and fetch(kept) is not None


def test_old_notes_leave_the_trash_after_30_days(client, add, fetch):
    old = add("Ancient", deleted_at="2026-09-19 08:00:00")     # 31 days ago
    recent = add("Recent", deleted_at="2026-09-21 10:00:00")   # 29 days ago
    client.get("/?view=trash")
    assert fetch(old) is None and fetch(recent) is not None


def test_trash_doesnt_touch_other_peoples_notes(post, add, other_user, fetch):
    theirs = add("Bob's", user_id=other_user, deleted_at="2026-10-19 10:00:00")
    post("/trash/empty")
    assert fetch(theirs) is not None
