"""A small Markdown renderer, written by hand, plus other text helpers.

Markdown is plain text with a few marks that mean formatting:

    # Heading          **bold**   *italic*   ~~struck~~   `code`
    - a bullet         1. a numbered item     - [ ] a checkbox
    > a quote          ---  a line            [a link](https://...)
    [[Another note]]   a link to another note
    #idea              a tag

render() works in two passes:
1. Blocks: each line is looked at on its own and grouped with its
   neighbours into paragraphs, lists, quotes and code blocks.
2. Inline marks: inside each line, bold, links and the rest.

Safety: the user's text is HTML-escaped *before* any tags are added, so
something like <script> shows up as text instead of running. Every tag in
the output was written by this file, never by the user.
"""
import html
import re

from markupsafe import Markup, escape

# ---------- Block patterns (one line each) ----------
HEADING = re.compile(r"(#{1,3})\s+(.+)")          # "# Title": the space after # matters, "#tag" isn't a heading
RULE = re.compile(r"(-{3,}|\*{3,}|_{3,})")        # "---"
CHECK_ITEM = re.compile(r"\s*[-*+]\s+\[([ xX])\]\s+(.*)")  # "- [ ] buy milk", "- [x] done"
BULLET = re.compile(r"\s*[-*+]\s+(.*)")           # "- item"
NUMBERED = re.compile(r"\s*\d{1,9}[.)]\s+(.*)")   # "1. item" or "1) item"
QUOTE = re.compile(r">\s?(.*)")                   # "> quoted"
FENCE = "```"                                     # a line starting with ``` opens or closes a code block

# ---------- Inline patterns ----------
CODE_SPAN = re.compile(r"`([^`\n]+)`")
WIKILINK = re.compile(r"\[\[([^\[\]\n]{1,120})\]\]")
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
# A web address on its own. It stops at an escaped quote (&#34; or &#39;),
# and can't end with punctuation, so the full stop in "see
# https://example.com." stays outside the link.
BARE_URL = re.compile(r"\bhttps?://(?:(?!&#\d+;)[^\s<\"'])+(?<![.,:;!?)\]])")
# (?=\S) and (?<=\S): the text inside must not start or end with a space, so
# "2 * 3 * 4" isn't italic.
BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
# *one star* or _underscores_. The underscores need a non-letter on both
# sides, so snake_case_names are left alone.
ITALIC = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])|(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)")
# A #tag starts with a letter, and can't follow a letter, / or & so that
# page#section, example.com/#top and HTML codes like &#39; aren't tags.
HASHTAG = re.compile(r"(?<![\w/&#])#([^\W\d_][\w-]{0,29})")
WORD = re.compile(r"\w+(?:['’-]\w+)*")            # "don't" and "well-known" count as one word

# Only these kinds of links are allowed, so a link like "javascript:..." can't run code.
SAFE_URL = re.compile(r"(https?://|mailto:)", re.IGNORECASE)

WORDS_PER_MINUTE = 200


def render(text, note_link=None, tag_url=None):
    """Turn Markdown text into safe HTML (a Markup string, which Jinja won't escape again).

    note_link(title) -> (url, exists) builds [[links]]. tag_url(name) -> url
    makes #tags clickable. Both are optional, so tests can render plain text.
    """
    html_parts = []
    kind, items = None, []  # the block being built, like ("ul", ["<li>...</li>"])

    def flush():
        """Finish the open block (paragraph, list or quote) and start fresh."""
        nonlocal kind, items
        if kind == "p":
            html_parts.append("<p>" + "<br>".join(items) + "</p>")
        elif kind == "quote":
            html_parts.append("<blockquote><p>" + "<br>".join(items) + "</p></blockquote>")
        elif kind in ("ul", "ol"):
            html_parts.append(f"<{kind}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{kind}>")
        elif kind == "checks":
            html_parts.append('<ul class="checklist">' + "".join(items) + "</ul>")
        kind, items = None, []

    def add(new_kind, item):
        """Add a line to the open block, first closing it if it's a different kind."""
        nonlocal kind
        if kind != new_kind:
            flush()
            kind = new_kind
        items.append(item)

    def inline(line):
        return render_inline(line, note_link, tag_url)

    lines = clean(text).split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith(FENCE):
            # A code block: copy every line up to the closing ``` as it is.
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(FENCE):
                code.append(lines[i])
                i += 1
            html_parts.append(f"<pre><code>{escape(chr(10).join(code))}</code></pre>")
            i += 1  # skip the closing ```
            continue

        if not stripped:
            flush()  # a blank line ends the paragraph or list
        elif match := HEADING.fullmatch(stripped):
            flush()
            # "# " becomes <h2>: the page's own title is the <h1>.
            level = len(match[1]) + 1
            html_parts.append(f"<h{level}>{inline(match[2])}</h{level}>")
        elif RULE.fullmatch(stripped):
            flush()
            html_parts.append("<hr>")
        elif match := CHECK_ITEM.fullmatch(line):
            done = match[1] != " "
            # data-line says which line of the text this box is on, so a
            # click can tick the right "- [ ]" (see toggle_checkbox()).
            add("checks",
                f'<li class="check{" done" if done else ""}"><label>'
                f'<input type="checkbox" data-line="{i}"{" checked" if done else ""}>'
                f"<span>{inline(match[2])}</span></label></li>")
        elif match := BULLET.fullmatch(line):
            add("ul", inline(match[1]))
        elif match := NUMBERED.fullmatch(line):
            add("ol", inline(match[1]))
        elif match := QUOTE.fullmatch(stripped):
            add("quote", inline(match[1]))
        else:
            add("p", inline(stripped))
        i += 1
    flush()
    return Markup("\n".join(html_parts))


def render_inline(text, note_link=None, tag_url=None):
    """The marks inside one line: code, links, #tags, bold, italic and strike.

    Finished pieces of HTML are swapped for a placeholder ("\\x00" + a
    number + "\\x00") while the other rules run, so a rule can't break HTML
    another one made: the * in a link's address won't turn into italics.
    """
    saved = []

    def keep(piece):
        saved.append(piece)
        return f"\x00{len(saved) - 1}\x00"

    text = str(escape(text))  # from here on, the user's < > & " ' are harmless

    text = CODE_SPAN.sub(lambda m: keep(f"<code>{m[1]}</code>"), text)

    def wikilink(m):
        title = html.unescape(m[1]).strip()
        if note_link is None:
            return keep(f'<span class="wikilink">{m[1]}</span>')
        url, exists = note_link(title)
        css = "wikilink" if exists else "wikilink missing"
        tip = "" if exists else ' title="No note with this title yet: click to make it"'
        return keep(f'<a class="{css}" href="{escape(url)}"{tip}>{m[1]}</a>')
    text = WIKILINK.sub(wikilink, text)

    def link(m):
        label, url = m[1], m[2]
        if not SAFE_URL.match(html.unescape(url)):
            return m[0]  # not a web or email link: leave the text as it was typed
        return keep(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>')
    text = LINK.sub(link, text)
    text = BARE_URL.sub(lambda m: keep(f'<a href="{m[0]}" target="_blank" rel="noopener noreferrer">{m[0]}</a>'), text)

    def hashtag(m):
        name = m[1].lower()
        if tag_url is None:
            return keep(f'<span class="hashtag">#{m[1]}</span>')
        return keep(f'<a class="hashtag" href="{escape(tag_url(name))}">#{m[1]}</a>')
    text = HASHTAG.sub(hashtag, text)

    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = STRIKE.sub(r"<del>\1</del>", text)
    text = ITALIC.sub(lambda m: f"<em>{m[1] or m[2]}</em>", text)

    # Put the saved pieces back.
    return re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m[1])], text)


# ---------- Reading text out of notes ----------

def clean(text):
    """Plain "\\n" line endings, and no NUL characters (they'd clash with the placeholders)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def lines_outside_code(text):
    """Yield (line number, line) for every line that isn't inside a ``` code block.

    Tags, [[links]] and checkboxes inside code are just examples, not the real thing.
    """
    in_code = False
    for number, line in enumerate(clean(text).split("\n")):
        if line.strip().startswith(FENCE):
            in_code = not in_code
        elif not in_code:
            yield number, line


def plain_text(text):
    """The note without its Markdown marks, for card previews and counting words."""
    out = []
    for _, line in lines_outside_code(text):
        line = line.strip()
        if RULE.fullmatch(line):
            continue
        # Drop the mark at the start of the line: "# ", "> ", "- [ ] ", "1. "...
        line = re.sub(r"^(#{1,3}\s+|>\s?|[-*+]\s+(?:\[[ xX]\]\s+)?|\d{1,9}[.)]\s+)", "", line)
        line = WIKILINK.sub(r"\1", line)
        line = LINK.sub(r"\1", line)
        line = BOLD.sub(r"\1", line)
        line = STRIKE.sub(r"\1", line)
        line = ITALIC.sub(lambda m: m[1] or m[2], line)
        line = CODE_SPAN.sub(r"\1", line)
        out.append(line)
    # Squash the blank lines a heading or list leaves behind.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def word_count(text):
    return len(WORD.findall(plain_text(text)))


def reading_minutes(words):
    """About how long a note takes to read, at least 1 minute."""
    return max(1, round(words / WORDS_PER_MINUTE))


def checklist_progress(text):
    """(done, total) for the note's "- [ ]" checkboxes, like (3, 5)."""
    done = total = 0
    for _, line in lines_outside_code(text):
        if match := CHECK_ITEM.fullmatch(line):
            total += 1
            done += match[1] != " "
    return done, total


def toggle_checkbox(text, line_number):
    """Tick or untick the checkbox on one line. Returns the new text, or None.

    None means that line isn't a checkbox (the note may have changed in
    another tab since the page was loaded), so nothing should be saved.
    """
    lines = clean(text).split("\n")
    code_free = dict(lines_outside_code(text))
    line = code_free.get(line_number)
    if line is None or not CHECK_ITEM.fullmatch(line):
        return None
    lines[line_number] = re.sub(r"\[([ xX])\]", lambda m: "[ ]" if m[1] != " " else "[x]", line, count=1)
    return "\n".join(lines)


def _without_code_spans(text):
    for _, line in lines_outside_code(text):
        yield CODE_SPAN.sub("", line)


def find_hashtags(text):
    """The #tags written in the text, lowercased, each once, in order."""
    tags = []
    for line in _without_code_spans(text):
        for name in HASHTAG.findall(BARE_URL.sub("", line)):
            if name.lower() not in tags:
                tags.append(name.lower())
    return tags


def rename_hashtag(text, old, new=None):
    """Change #old to #new everywhere in the text (outside code), ignoring case.

    With new=None the # is dropped instead ("#idea" -> "idea"), so deleting
    a tag keeps the word but stops it being a tag.
    """
    pattern = re.compile(rf"(?<![\w/&#])#{re.escape(old)}(?![\w-])", re.IGNORECASE)
    replacement = f"#{new}" if new else old
    lines = clean(text).split("\n")
    for number, line in lines_outside_code(text):
        lines[number] = pattern.sub(lambda m: replacement if new else m[0][1:], line)
    return "\n".join(lines)


def find_wikilinks(text):
    """The titles in [[Note title]] links, each once, in order."""
    titles = []
    for line in _without_code_spans(text):
        for title in WIKILINK.findall(line):
            title = " ".join(title.split())
            if title and title.casefold() not in [t.casefold() for t in titles]:
                titles.append(title)
    return titles


# ---------- Markdown files (export and import) ----------

def to_markdown_file(title, tags, body):
    """A note as a .md file, with "front matter" (title and tags) on top.

    Front matter is a block between two "---" lines that many notes apps
    (Obsidian, Jekyll, Hugo) read, so the tags survive the trip.
    """
    header = ["---", f"title: {title}"]
    if tags:
        header.append(f"tags: {', '.join(tags)}")
    header.append("---")
    return "\n".join(header) + "\n\n" + body + "\n"


def parse_markdown_file(text, filename="note.md"):
    """Read a .md file back into (title, tags, body).

    Without front matter, the title is the first "# Heading" (which is then
    taken out of the body), or else the file's name.
    """
    text = clean(text).lstrip("﻿")  # some editors put an invisible "BOM" at the start
    title, tags, body = "", [], text
    lines = text.split("\n")
    if lines and lines[0].strip() == "---" and "---" in [line.strip() for line in lines[1:]]:
        end = [line.strip() for line in lines].index("---", 1)
        for line in lines[1:end]:
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "title":
                title = value.strip("\"'")
            elif key == "tags":
                tags = [tag for tag in re.split(r"[\s,\[\]]+", value) if tag]
        body = "\n".join(lines[end + 1:])
    body = body.strip("\n")
    if not title:
        first = body.split("\n", 1)
        if match := HEADING.fullmatch(first[0].strip()):
            title = match[2].strip()
            body = first[1].strip("\n") if len(first) > 1 else ""
    if not title:
        title = re.sub(r"\.(md|markdown|txt)$", "", filename, flags=re.IGNORECASE).replace("_", " ").strip()
    return title, tags, body
