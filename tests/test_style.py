"""Checks on style.css: readable text on every note color, and a fixed logo.

WCAG AA asks for a contrast ratio of at least 4.5 for normal text. Pastels
often fail it, so this test works the ratio out for the text colors on
each note color, in the light and the dark look.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).parent.parent / "notes" / "static" / "style.css").read_text(encoding="utf-8")
COLORS = ["red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"]


def block(selector):
    """The text of the first CSS rule for `selector` (up to its closing brace)."""
    start = CSS.index(selector + " {")
    return CSS[start:CSS.index("\n}", start)]


def variable(css_block, name):
    return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", css_block).group(1)


def luminance(hex_color):
    """How bright a color looks, from 0 (black) to 1 (white), the WCAG way."""
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    light, dark = sorted([luminance(a), luminance(b)], reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("look", [":root", '[data-appearance="dark"]'])
@pytest.mark.parametrize("color", COLORS)
def test_text_is_readable_on_every_note_color(look, color):
    light = block(":root")
    css = block(look)
    background = variable(css, f"note-{color}") if look != ":root" else variable(light, f"note-{color}")
    for name in ["text", "muted"]:
        ink = variable(css, name)
        assert contrast(ink, background) >= 4.5, f"--{name} on {color} in {look}: {contrast(ink, background):.2f}"


def test_dark_look_is_written_the_same_twice():
    """Dark mode is written for "Dark" and for "Match my device": the two must match."""
    dark = block('[data-appearance="dark"]')
    system = CSS.split('[data-appearance="system"] {')[1].split("}")[0]
    names = lambda text: dict(re.findall(r"(--[\w-]+):\s*([^;]+);", text))
    assert names(dark) == names(system)


def test_hidden_always_hides():
    """app.js hides buttons with the hidden attribute; classes like .btn mustn't undo that."""
    assert re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important;", CSS)


def test_nothing_restyles_the_logo():
    """The logo is a fixed image: no filter, blend or theme variable may touch it."""
    for rule in re.findall(r"([^{}]*brand-logo[^{}]*)\{([^}]*)\}", CSS):
        assert not re.search(r"filter|mix-blend|var\(--accent", rule[1]), rule
