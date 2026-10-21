"""Search: the full-text index (FTS5), filters, and the LIKE fallback."""
import pytest

from conftest import logged_in_client, make_app
from notes.search import fts_expression, parse_query


def titles(client, url):
    """The note titles on a page, in order."""
    html = client.get(url).get_data(as_text=True)
    return [part.split("</h3>")[0] for part in html.split('<h3 class="card-title">')[1:]]


def test_parse_query():
    query = parse_query('tag:Work #ideas is:pinned color:blue has:checklist "next steps" budget - color:plaid')
    assert query["tags"] == ["work", "ideas"]
    assert query["pinned"] and query["checklist"]
    assert query["colors"] == ["blue"]
    assert query["phrases"] == ["next steps"]
    assert query["words"] == ["budget", "color:plaid"]  # "-" alone is skipped


def test_fts_expression_quotes_everything():
    assert fts_expression(parse_query('bud say"hi" "two words"')) == '"bud"* "say""hi"""* "two words"'


def test_finds_words_and_word_starts(client, add):
    add("Monthly budget", body="rent and food")
    add("Recipes", body="adobo")
    assert titles(client, "/?q=budget") == ["Monthly <mark>budget</mark>"]
    assert titles(client, "/?q=bud") == ["Monthly <mark>budget</mark>"]   # still typing
    assert titles(client, "/?q=food rent") == ["Monthly budget"]          # all words, any order
    assert titles(client, "/?q=running") == []


def test_word_endings_match(client, add):
    add("Morning", body="I like running")
    assert titles(client, "/?q=run") == ["Morning"]
    assert titles(client, "/?q=runs") == ["Morning"]  # the porter tokenizer: runs ~ running


def test_title_matches_rank_first(client, add):
    add("Garden notes", body="tomatoes need sun", updated_at="2026-10-20 08:59:00")
    add("Tomatoes", body="buy seeds", updated_at="2026-01-01 00:00:00")
    assert titles(client, "/?q=tomatoes") == ["<mark>Tomatoes</mark>", "Garden notes"]


def test_snippets_mark_matches_and_stay_safe(client, add):
    add("Safe", body="first line\n**Important**: the <script>secret</script> plan")
    html = client.get("/?q=secret").get_data(as_text=True)
    assert "<mark>secret</mark>" in html
    assert "&lt;script&gt;" in html and "<script>secret" not in html
    assert "**" not in html.split('class="card-snippet"')[1].split("</p>")[0]


def test_search_only_finds_your_notes_outside_the_trash(client, add, other_user):
    add("Mine", body="pineapple")
    add("Bob's", body="pineapple", user_id=other_user)
    add("Trashed", body="pineapple", deleted_at="2026-10-19 10:00:00")
    add("Archived", body="pineapple", archived=1)
    assert titles(client, "/?q=pineapple") == ["Mine"]
    assert titles(client, "/?view=archive&q=pineapple") == ["Archived"]
    assert titles(client, "/?view=trash&q=pineapple") == ["Trashed"]


def test_index_follows_edits_and_deletes(client, post, add):
    note_id = add("Changing", body="apple")
    post(f"/notes/{note_id}", {"title": "Changing", "body": "banana"})
    assert titles(client, "/?q=apple") == []
    assert titles(client, "/?q=banana") == ["Changing"]
    post(f"/notes/{note_id}/trash")
    post(f"/notes/{note_id}/purge")
    assert titles(client, "/?view=trash&q=banana") == []


def test_filters(client, add):
    add("Work list", body="- [ ] email", tags=["work"], color="blue", pinned=1)
    add("Home list", body="plain", tags=["home"], color="green")
    assert titles(client, "/?q=tag:work") == ["Work list"]
    assert titles(client, "/?q=%23home") == ["Home list"]
    assert titles(client, "/?q=is:pinned") == ["Work list"]
    assert titles(client, "/?q=color:green") == ["Home list"]
    assert titles(client, "/?q=has:checklist") == ["Work list"]
    assert titles(client, "/?q=list tag:home") == ["Home <mark>list</mark>"]
    assert titles(client, "/?tag=work") == ["Work list"]


def test_phrases(client, add):
    add("A", body="next steps are clear")
    add("B", body="steps next")
    assert titles(client, '/?q="next steps"') == ["A"]


@pytest.mark.parametrize("text", ['"', "*", "-", "AND", "NEAR(", "a:b:c", "(((", "'"])
def test_odd_searches_dont_crash(client, add, text):
    add("Something", body="text")
    assert client.get("/", query_string={"q": text}).status_code == 200


# ---------- Without FTS5 ----------

@pytest.fixture
def like_client(tmp_path):
    """A logged-in client for an app that searches with LIKE instead of FTS5."""
    app = make_app(tmp_path, USE_FTS=False)
    assert app.config["USE_FTS"] is False
    return app, logged_in_client(app)


def test_like_search_finds_and_marks(like_client):
    from conftest import insert_note
    app, client = like_client
    insert_note(app, "Monthly budget", body="rent is 50% of pay")
    insert_note(app, "Other", body="nothing here")
    assert titles(client, "/?q=budget") == ["Monthly <mark>budget</mark>"]
    html = client.get("/?q=50%25").get_data(as_text=True)
    assert "<mark>50%</mark>" in html
    assert titles(client, "/?q=5_") == []  # _ is a plain character here, not a wildcard
