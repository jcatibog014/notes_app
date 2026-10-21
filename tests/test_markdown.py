"""The hand-written Markdown renderer and text helpers (no Flask needed)."""
from notes.markdown import (checklist_progress, find_hashtags, find_wikilinks, parse_markdown_file,
                            plain_text, reading_minutes, rename_hashtag, render, to_markdown_file,
                            toggle_checkbox, word_count)


def test_html_is_escaped_not_run():
    html = render('<script>alert("hi")</script> & <b>bold</b>')
    assert "<script>" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


def test_headings_need_a_space_after_the_hash():
    assert "<h2>Groceries</h2>" in render("# Groceries")
    assert "<h3>Fruit</h3>" in render("## Fruit")
    assert "<h4>Red</h4>" in render("### Red")
    assert "<h2>" not in render("#groceries")  # a tag, not a heading


def test_inline_marks():
    html = render("**bold** *italic* _also_ ~~gone~~ `code`")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html and "<em>also</em>" in html
    assert "<del>gone</del>" in html
    assert "<code>code</code>" in html


def test_marks_that_are_not_formatting():
    assert "<em>" not in render("2 * 3 * 4 = 24")
    assert "<em>" not in render("my_snake_case_name")
    # Inside `code`, stars stay stars.
    assert "<code>**not bold**</code>" in render("`**not bold**`")


def test_lists_quotes_and_lines():
    html = render("- one\n- two\n\n1. first\n2. second\n\n> wise words\n\n---")
    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<ol><li>first</li><li>second</li></ol>" in html
    assert "<blockquote><p>wise words</p></blockquote>" in html
    assert "<hr>" in html


def test_paragraph_lines_are_kept():
    assert render("line one\nline two") == "<p>line one<br>line two</p>"


def test_checklist_items_know_their_line():
    html = render("Shopping\n- [ ] eggs\n- [x] milk")
    assert 'data-line="1"' in html and 'data-line="2"' in html
    assert '<li class="check done">' in html
    assert html.count("checked") == 1


def test_code_block_is_copied_as_is():
    html = render("```\n# not a heading\n<b>x</b>\n```\nafter")
    assert "<pre><code># not a heading\n&lt;b&gt;x&lt;/b&gt;</code></pre>" in html
    assert "<p>after</p>" in html


def test_only_web_and_email_links_are_made():
    html = render("[site](https://example.com/?a=1&b=2) [bad](javascript:alert(1)) [mail](mailto:a@b.co)")
    assert 'href="https://example.com/?a=1&amp;b=2"' in html
    assert 'href="mailto:a@b.co"' in html
    assert "javascript" not in html.split("[bad]")[0]
    assert 'href="javascript' not in html


def test_bare_urls_become_links_without_the_full_stop():
    html = render("See https://example.com/page.")
    assert '<a href="https://example.com/page"' in html
    assert "</a>." in html


def test_wikilinks_use_the_given_lookup():
    def lookup(title):
        return ("/notes/7", True) if title == "Budget" else ("/notes/new?title=x", False)
    html = render("See [[Budget]] and [[Nowhere]]", note_link=lookup)
    assert '<a class="wikilink" href="/notes/7">Budget</a>' in html
    assert 'class="wikilink missing"' in html


def test_hashtags():
    html = render("Plan #trip-2026 now", tag_url=lambda name: f"/?tag={name}")
    assert '<a class="hashtag" href="/?tag=trip-2026">#trip-2026</a>' in html
    # Not tags: a number, a page section, and the &#39; an apostrophe becomes.
    html = render("step #1, example.com/#top, page#part, it's")
    assert "hashtag" not in html


def test_plain_text_and_counting():
    text = "# Title\n- [x] **Don't** stop\n> well-known [link](https://x.y)"
    assert plain_text(text) == "Title\nDon't stop\nwell-known link"
    assert word_count(text) == 5
    assert reading_minutes(0) == 1
    assert reading_minutes(1000) == 5


def test_checklist_progress_ignores_code():
    assert checklist_progress("- [x] a\n- [ ] b\n* [X] c\n```\n- [ ] example\n```") == (2, 3)


def test_toggle_checkbox():
    text = "Trip\n- [ ] passport\n- [x] tickets"
    assert toggle_checkbox(text, 1) == "Trip\n- [x] passport\n- [x] tickets"
    assert toggle_checkbox(text, 2) == "Trip\n- [ ] passport\n- [ ] tickets"
    assert toggle_checkbox(text, 0) is None    # not a checkbox
    assert toggle_checkbox(text, 9) is None    # no such line
    assert toggle_checkbox("```\n- [ ] x\n```", 1) is None  # inside code


def test_find_hashtags():
    text = "#Work and #ideas, again #work\n`#notatag`\n```\n#alsonot\n```\nhttps://x.com/a#frag"
    assert find_hashtags(text) == ["work", "ideas"]


def test_find_wikilinks_once_each():
    assert find_wikilinks("[[Budget]] [[budget]] [[ Trip  plan ]]") == ["Budget", "Trip plan"]


def test_rename_hashtag():
    text = "#Idea and #ideas and #idea\n```\n#idea\n```"
    assert rename_hashtag(text, "idea", "plan") == "#plan and #ideas and #plan\n```\n#idea\n```"
    assert rename_hashtag("my #Idea", "idea") == "my Idea"  # deleting keeps the word


def test_markdown_file_round_trip():
    text = to_markdown_file("Trip", ["travel", "fun"], "- [ ] pack")
    assert text.startswith("---\ntitle: Trip\ntags: travel, fun\n---\n")
    assert parse_markdown_file(text) == ("Trip", ["travel", "fun"], "- [ ] pack")


def test_markdown_file_without_front_matter():
    assert parse_markdown_file("# Recipes\nAdobo") == ("Recipes", [], "Adobo")
    assert parse_markdown_file("just text", "my_notes.md") == ("my notes", [], "just text")
