"""Text-only bars: numbers in, rich Text out.

Drawing lives here rather than in the app for one reason: a proportion bar is
the easiest place in this codebase to lie by accident, and a pure function can
be tested against exact expected glyphs without a terminal. Nothing in this
module imports Textual.

* The bar is scaled to the largest row the caller passes, and the percentage
  beside it is its share of the window — two different denominators, each
  labelled.
* A zero value is a trace, not a one-pixel bar. Nothing used reads as nothing.
"""

from __future__ import annotations

from rich.text import Text

BLOCK = "█"
TRACE = "░"


def share_bar(value: int, total: int, *, width: int = 12, style: str = "cyan") -> Text:
    """A proportion bar: the reader should not have to divide two numbers."""
    bar = Text()
    if total <= 0 or value <= 0:
        bar.append(TRACE * width, style="grey30")
        return bar
    filled = round(max(0.0, min(1.0, value / total)) * width)
    filled = max(1, min(width, filled))
    bar.append(BLOCK * filled, style=style)
    bar.append(TRACE * (width - filled), style="grey30")
    return bar


def pct(value: int, total: int) -> str:
    if total <= 0:
        return "—"
    return f"{value / total * 100:.0f}%"
