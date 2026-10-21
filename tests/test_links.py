"""[[Note title]] links between notes, and backlinks."""


def test_links_point_to_the_note_with_that_title(client, post, add):
    budget = add("Monthly Budget")
    post("/notes/new", {"title": "Trip", "body": "Costs are in [[monthly budget]]"})
    html = client.get("/notes/2").get_data(as_text=True)
    assert f'<a class="wikilink" href="/notes/{budget}">monthly budget</a>' in html


def test_a_link_to_a_missing_note_offers_to_make_it(client, post):
    post("/notes/new", {"title": "Trip", "body": "See [[Packing list]]"})
    html = client.get("/notes/1").get_data(as_text=True)
    assert 'class="wikilink missing" href="/notes/new?title=Packing+list"' in html
    page = client.get("/notes/new?title=Packing+list").get_data(as_text=True)
    assert 'value="Packing list"' in page


def test_backlinks(client, post, add):
    target = add("Budget")
    post("/notes/new", {"title": "Trip", "body": "[[Budget]]"})
    post("/notes/new", {"title": "Groceries", "body": "[[budget]] again"})
    post("/notes/new", {"title": "Unrelated", "body": "nothing"})
    html = client.get(f"/notes/{target}").get_data(as_text=True)
    section = html.split("Linked From")[1]
    assert ">Trip</a>" in section and ">Groceries</a>" in section
    assert "Unrelated" not in section


def test_links_from_notes_in_the_trash_dont_count(client, post, add):
    target = add("Budget")
    post("/notes/new", {"title": "Trip", "body": "[[Budget]]"})
    post("/notes/2/trash")
    assert "Linked From" not in client.get(f"/notes/{target}").get_data(as_text=True)
