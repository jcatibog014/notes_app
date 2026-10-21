"""The Markdown renderer is the app's biggest security surface: everything a
note says ends up in the page. These tests attack it on purpose.

The fuzz test throws thousands of random mixes of tricky pieces at render()
and checks the HTML that comes out: only tags and attributes this app
writes, only safe links, and every tag properly closed.
"""
import random
from html.parser import HTMLParser

import pytest

from notes.markdown import render, render_inline


def link(title):
    return f"/notes/new?title={title}", False


def tag_url(name):
    return f"/?tag={name}"


@pytest.mark.parametrize("text", [
    "[x](javascript:alert(1))",
    "[x](JavaScript:alert(1))",
    "[x](  javascript:alert(1))",
    "[x](jav&#x61;script:alert(1))",
    "[x](data:text/html;base64,PHNjcmlwdD4=)",
    "[x](vbscript:msgbox(1))",
    "[x](//evil.example)",
    "<a href=javascript:alert(1)>x</a>",
    "![x](javascript:alert(1))",
])
def test_unsafe_links_are_never_made(text):
    html = render(text)
    assert 'href="' not in html


def test_quotes_cant_break_out_of_an_attribute():
    html = render('[x](https://a.co/"onmouseover="alert(1))')
    assert "onmouseover=" not in html.replace("&#34;onmouseover=&#34;", "")
    assert '" onmouseover' not in html


def test_html_in_every_kind_of_block_is_escaped():
    text = "# <b>h</b>\n- <i>li</i>\n> <u>q</u>\n- [ ] <s>c</s>\n```\n<script>\n```\n`<code>`"
    html = render(text)
    for raw in ["<b>", "<i>", "<u>", "<s>", "<script>", "<code><code>"]:
        assert raw not in html


def test_code_blocks_keep_backticks_and_stars():
    html = render("```\nuse `ticks` and **stars**\n```")
    assert "<pre><code>use `ticks` and **stars**</code></pre>" in html


def test_code_spans_with_html_and_marks():
    assert render_inline("`<b>**x**</b>`") == "<code>&lt;b&gt;**x**&lt;/b&gt;</code>"


def test_bold_italic_together():
    assert render_inline("***both***") == "<strong><em>both</em></strong>"
    assert render_inline("*a **b** c*") == "<em>a <strong>b</strong> c</em>"
    assert render_inline("**a *b* c**") == "<strong>a <em>b</em> c</strong>"


def test_overlapping_marks_dont_cross():
    html = render_inline("**a *b** c*")
    assert "<strong>a *b</strong> c*" == html  # the italic would cross, so it stays as typed


def test_strike_inside_words():
    assert render_inline("un~~do~~ne") == "un<del>do</del>ne"


def test_wikilink_titles_are_escaped():
    html = render('[[<img src=x onerror=alert(1)>]]', note_link=link)
    assert "<img" not in html


def test_null_characters_cant_fake_placeholders():
    html = render_inline("\x000\x00 and `code`")
    assert "\x00" not in html


# ---------- Fuzzing ----------

PIECES = ["*", "**", "***", "_", "~~", "`", "```", "[", "]", "(", ")", "[[", "]]", "#", "#tag", "<", ">", "&",
          '"', "'", "javascript:", "data:", "https://x.y/a?b=1&c=2", "mailto:a@b.c", "\n", "\n\n", "- [ ] ",
          "- [x] ", "- ", "1. ", "> ", "# ", "---", "a", "word", " ", "</script>", "<script>", "onerror=",
          "\x00", "&#39;", "&lt;", "](", ")[", "**[", "]**"]

ALLOWED = {
    "p": set(), "br": set(), "h2": set(), "h3": set(), "h4": set(), "ul": {"class"}, "ol": set(),
    "li": {"class"}, "blockquote": set(), "pre": set(), "code": set(), "hr": set(), "strong": set(),
    "em": set(), "del": set(), "label": set(), "span": {"class"},
    "a": {"href", "class", "target", "rel", "title"},
    "input": {"type", "data-line", "checked"},
}
VOID = {"br", "hr", "input"}


class Checker(HTMLParser):
    """Reads the HTML and fails the test on anything this app shouldn't make."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        assert tag in ALLOWED, f"unexpected tag <{tag}>"
        for name, value in attrs:
            assert name in ALLOWED[tag], f"unexpected attribute {name} on <{tag}>"
            if name == "href":
                assert value.startswith(("https://", "http://", "mailto:", "/")), f"unsafe link {value!r}"
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, f"</{tag}> closes {self.stack[-1:] or 'nothing'}"
        self.stack.pop()


@pytest.mark.parametrize("seed", range(20))
def test_fuzz_random_markdown_makes_only_safe_well_formed_html(seed):
    rng = random.Random(seed)  # seeded, so a failure can be reproduced
    for _ in range(150):
        text = "".join(rng.choice(PIECES) for _ in range(rng.randint(1, 40)))
        html = render(text, note_link=link, tag_url=tag_url)
        checker = Checker()
        try:
            checker.feed(str(html))
            checker.close()
            assert not checker.stack, f"unclosed {checker.stack}"
        except AssertionError as error:
            raise AssertionError(f"{error}\ninput: {text!r}\noutput: {html!r}") from None
