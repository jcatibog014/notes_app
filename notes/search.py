"""Finding notes: the view (All, Pinned, Archive, Trash), filters and search.

What's typed in the search box is split into two kinds of parts:

    tag:work  #work      only notes with that tag
    is:pinned            only pinned notes
    color:blue           only blue notes
    has:checklist        only notes with - [ ] checkboxes
    "exact phrase"       these words, next to each other
    budget plan          notes with all of these words (or words starting with them)

The words go to SQLite's full-text index (FTS5, see schema_fts.sql), which
ranks the best matches first and marks where they were found. If this
SQLite has no FTS5, a slower LIKE search does the same job, minus the ranking.
"""
import re
from difflib import get_close_matches

from markupsafe import Markup, escape

from .markdown import plain_text
from .validation import NOTE_COLORS, SORTS

# The filters, and the values each one takes (None = any value, like a tag name).
FILTERS = {"tag": None, "is": ["pinned"], "color": list(NOTE_COLORS), "has": ["checklist"]}

# A "quoted phrase", or one run of characters without spaces.
TOKEN = re.compile(r'"([^"]*)"?|(\S+)')

# Markers put around each match while the text is still plain. They're
# control characters, so they can't be typed, and they survive escape().
START, END = "\x02", "\x03"

SNIPPET_RADIUS = 70  # characters of context on each side of a match (LIKE search)


def parse_query(text):
    """Split the search box's text into filters and words.

    >>> parse_query('tag:work "next steps" budget')["phrases"]
    ['next steps']
    """
    query = {"words": [], "phrases": [], "tags": [], "colors": [], "pinned": False, "checklist": False,
             "suggestions": []}
    for match in TOKEN.finditer(text or ""):
        if match[1] is not None:  # a "quoted phrase"
            phrase = " ".join(match[1].split())
            if re.search(r"\w", phrase):
                query["phrases"].append(phrase)
            continue
        token = match[2]
        key, colon, value = token.partition(":")
        key, value = key.lower(), value.lower().lstrip("#")
        if colon and key == "tag" and value:
            query["tags"].append(value)
        elif colon and key == "is" and value == "pinned":
            query["pinned"] = True
        elif colon and key == "color" and value in NOTE_COLORS:
            query["colors"].append(value)
        elif colon and key == "has" and value in ("checklist", "checkbox", "todo"):
            query["checklist"] = True
        elif token.startswith("#") and len(token) > 1:
            query["tags"].append(token[1:].lower())
        elif re.search(r"\w", token):  # skip stray punctuation like "-"
            query["words"].append(token)
            if colon and (fix := suggest_filter(key, value)):
                query["suggestions"].append((token, fix))
    return query


def suggest_filter(key, value):
    """A fix for something that looks like a mistyped filter, or None.

    "tags:work" -> "tag:work", "is:pin" -> "is:pinned", "color:purpel" ->
    "color:purple". difflib.get_close_matches() finds the known word that
    is most like what was typed.
    """
    if not value:
        return None
    keys = get_close_matches(key, FILTERS, n=1, cutoff=0.6)
    if not keys:
        return None
    choices = FILTERS[keys[0]]
    if choices is None:
        return f"{keys[0]}:{value}"
    values = [value] if value in choices else get_close_matches(value, choices, n=1, cutoff=0.5)
    return f"{keys[0]}:{values[0]}" if values else None


def toggle_token(text, token):
    """Add `token` (like "is:pinned") to the search text, or take it out if it's there.

    Used by the filter chips under the search box: each chip is a link to
    the same search with its filter switched on or off.
    """
    tokens = [match[0] for match in TOKEN.finditer(text or "")]
    if token.lower() in [t.lower() for t in tokens]:
        tokens = [t for t in tokens if t.lower() != token.lower()]
    else:
        tokens.append(token)
    return " ".join(tokens)


def fts_expression(query):
    """Turn the words and phrases into an FTS5 search, like: "budget"* "next steps".

    Each one is put in double quotes, so characters that mean something to
    FTS5 (like - or *) are searched as text instead of breaking the search.
    A " inside is written twice, which is how FTS5 escapes it. The * after
    a word also finds longer words that start with it, so "bud" finds
    "budget" while you're still typing. Each word is searched both ways,
    ("bud" OR "bud"*): a note with the exact word matches twice, so its
    score is better and it comes first.
    """
    parts = []
    for word in query["words"]:
        quoted = '"' + word.replace('"', '""') + '"'
        parts.append(f"({quoted} OR {quoted}*)")
    parts += ['"' + phrase.replace('"', '""') + '"' for phrase in query["phrases"]]
    # A space means AND between plain words, but not next to (brackets), so write it out.
    return " AND ".join(parts)


def like_pattern(text):
    """"50%" -> "%50\\%%": % and _ are LIKE's wildcards, so escape them first."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def find_notes(db, user_id, where, text="", tag=None, use_fts=True, sort="updated"):
    """Return (notes, query): the user's notes in a view, filtered and searched.

    where   -- SQL for the view, like "deleted_at IS NULL AND archived = 0".
               It comes from notes.VIEWS, never from the user.
    text    -- what was typed in the search box
    tag     -- the tag picked in the sidebar, if any
    sort    -- a key of SORTS. Searches are sorted by best match instead.

    Each note is a dict. When words were searched, it also has title_html
    and snippet_html with the matches in <mark>.
    """
    query = parse_query(text)
    if tag:
        query["tags"].append(tag)

    conditions = ["notes.user_id = ?", where]
    params = [user_id]
    for name in query["tags"]:
        conditions.append(
            "EXISTS (SELECT 1 FROM note_tags JOIN tags ON tags.id = note_tags.tag_id"
            " WHERE note_tags.note_id = notes.id AND tags.name = ?)"
        )
        params.append(name)
    if query["pinned"]:
        conditions.append("notes.pinned = 1")
    if query["colors"]:
        conditions.append(f"notes.color IN ({', '.join('?' for _ in query['colors'])})")
        params += query["colors"]
    if query["checklist"]:
        conditions.append("(notes.body LIKE '%[ ]%' OR notes.body LIKE '%[x]%')")

    searching = bool(query["words"] or query["phrases"])
    if searching and use_fts:
        rows = search_fts(db, query, conditions, params)
    elif searching:
        rows = search_like(db, query, conditions, params)
    else:
        order = SORTS.get(sort, SORTS["updated"])[1]
        rows = db.execute(
            f"SELECT notes.* FROM notes WHERE {' AND '.join(conditions)}"
            f" ORDER BY notes.pinned DESC, {order}",
            params,
        ).fetchall()
        rows = [dict(row) for row in rows]
    return rows, query


def search_fts(db, query, conditions, params):
    """Search with the full-text index. Best matches first.

    bm25() scores how well a note matches. Lower is better, and a match in
    the title counts 8 times as much as one in the text. highlight() and
    snippet() mark the matched words with START and END.
    """
    rows = db.execute(
        "SELECT notes.*,"
        f" highlight(notes_fts, 0, '{START}', '{END}') AS title_marked,"
        f" snippet(notes_fts, 1, '{START}', '{END}', '…', 18) AS snippet_marked"
        " FROM notes_fts JOIN notes ON notes.id = notes_fts.rowid"
        f" WHERE notes_fts MATCH ? AND {' AND '.join(conditions)}"
        " ORDER BY bm25(notes_fts, 8.0, 1.0)",
        [fts_expression(query), *params],
    ).fetchall()
    notes = []
    for row in rows:
        note = dict(row)
        note["title_html"] = marked(note.pop("title_marked"))
        snippet = note.pop("snippet_marked")
        # The snippet is a piece of the raw Markdown. Take the marks out, so
        # it reads like the card would.
        note["snippet_html"] = marked(squash(plain_text(snippet))) if START in snippet else None
        notes.append(note)
    return notes


def search_like(db, query, conditions, params):
    """The search for an SQLite without FTS5: every word must appear somewhere."""
    terms = query["words"] + query["phrases"]
    for term in terms:
        conditions = conditions + ["(notes.title LIKE ? ESCAPE '\\' OR notes.body LIKE ? ESCAPE '\\')"]
        params = params + [like_pattern(term)] * 2
    rows = db.execute(
        f"SELECT notes.* FROM notes WHERE {' AND '.join(conditions)}"
        " ORDER BY notes.pinned DESC, notes.updated_at DESC",
        params,
    ).fetchall()
    notes = []
    for row in rows:
        note = dict(row)
        note["title_html"] = marked(mark_terms(note["title"], terms))
        snippet = make_snippet(squash(plain_text(note["body"])), terms)
        note["snippet_html"] = marked(snippet) if snippet else None
        notes.append(note)
    # Notes with a match in the title first, like the FTS ranking does.
    # (sort() keeps the order of notes that tie, so the rest stay newest first.)
    notes.sort(key=lambda note: "<mark>" not in note["title_html"])
    return notes


def mark_terms(text, terms):
    """Put START/END around every place a term appears (ignoring case)."""
    if not terms:
        return text
    pattern = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    return re.sub(pattern, lambda m: START + m[0] + END, text, flags=re.IGNORECASE)


def make_snippet(text, terms):
    """A short piece of the text around the first match, with every match marked."""
    marked_text = mark_terms(text, terms)
    first = marked_text.find(START)
    if first == -1:
        return None
    start = max(0, first - SNIPPET_RADIUS)
    end = min(len(marked_text), first + SNIPPET_RADIUS * 2)
    # Don't cut a match in half at the end.
    if marked_text.rfind(START, start, end) > marked_text.rfind(END, start, end):
        end = marked_text.find(END, end) + 1
    piece = marked_text[start:end]
    return ("…" if start > 0 else "") + piece + ("…" if end < len(marked_text) else "")


def squash(text):
    """Join lines and runs of spaces into single spaces: snippets are one paragraph."""
    return " ".join(text.split())


def marked(text):
    """Escape the text, then turn the START/END markers into <mark> tags.

    Escaping first keeps it safe: the user's < > & can't make HTML, and the
    only tags in the result are the <mark>s added here.
    """
    return Markup(str(escape(text)).replace(START, "<mark>").replace(END, "</mark>"))
