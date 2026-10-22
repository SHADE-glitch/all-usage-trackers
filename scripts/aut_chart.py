"""Text-only charts: numbers in, rich Text out.

Drawing lives here rather than in the app for one reason: a chart is the easiest
place in this codebase to lie by accident, and a pure function can be tested
against exact expected glyphs without a terminal. Nothing in this module imports
Textual.

Two rules the callers rely on:

* Every series in one chart shares one y-scale. A 8M source and an 81M source
  must not draw the same bar; that is the whole point of putting them together.
* A zero bucket is a gap, not a one-pixel bar. An empty hour reads as empty.
"""

from __future__ import annotations

from rich.text import Text

BLOCK = "█"
TRACE = "░"


def stacked_chart(
    series: dict[str, list[int]],
    labels: list[str],
    *,
    width: int,
    height: int,
    styles: dict[str, str] | None = None,
) -> list[Text]:
    """A stacked bar chart with a y axis, an x axis and one shared scale.

    series: source key -> one value per bucket, all lists the same length.
    labels: one short label per bucket ("14", "10-18").
    width:  total characters available, including the y-axis gutter.
    height: bar rows, not counting the axis or the label line.
    """
    styles = styles or {}
    height = max(2, height)
    labels = list(labels)
    keys = [k for k in series if any(v > 0 for v in series[k])]
    if not keys or not labels:
        return [Text("no usage in this window", style="dim")]

    n = len(labels)
    values = {}
    for key in keys:
        row = list(series[key])[:n]
        values[key] = row + [0] * (n - len(row))
    totals = [sum(values[k][i] for k in keys) for i in range(n)]

    # Narrow terminals: merge neighbouring buckets rather than dropping them, so
    # the shape of the window survives even at 60 columns.
    axis_w = max(4, len(_short(max(totals) or 1)))
    plot_w = max(4, width - axis_w - 2)
    if n > plot_w:
        group = -(-n // plot_w)
        values = {k: [_sum(v[i:i + group]) for i in range(0, n, group)] for k, v in values.items()}
        totals = [_sum(totals[i:i + group]) for i in range(0, n, group)]
        labels = [labels[i] for i in range(0, n, group)]
        n = len(totals)

    top = max(totals) or 1
    # Bar heights, then each column split into per-source segments.
    columns: list[list[str]] = []
    for i in range(n):
        total = totals[i]
        if total <= 0:
            columns.append([])
            continue
        rows = max(1, round(total / top * height))
        rows = min(rows, height)
        segments: list[tuple[str, int]] = []
        used = 0
        live = [k for k in keys if values[k][i] > 0]
        for pos, key in enumerate(live):
            if pos == len(live) - 1:
                size = rows - used
            else:
                size = round(values[key][i] / total * rows)
                size = max(0, min(size, rows - used))
            segments.append((key, size))
            used += size
        column: list[str] = []
        for key, size in segments:
            column.extend([key] * size)
        columns.append(column)

    grid = _grid(columns, n, height, keys, styles)
    gutter = [fmt_axis(top), fmt_axis(top / 2), "0"]
    out: list[Text] = []
    for r in range(height):
        line = Text()
        if r == 0:
            line.append(gutter[0].rjust(axis_w) + " ┤", style="grey37")
        elif r == height // 2:
            line.append(gutter[1].rjust(axis_w) + " ┤", style="grey37")
        elif r == height - 1:
            # The zero line is the one a reader uses to judge a bar's height.
            line.append(gutter[2].rjust(axis_w) + " ┤", style="grey37")
        else:
            line.append(" " * axis_w + " │", style="grey37")
        line.append_text(grid[r])
        out.append(line)

    rule = Text(" " * axis_w + " └" + "─" * n, style="grey37")
    out.append(rule)
    out.append(_x_labels(labels, axis_w + 2, plot_w))
    return out


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


def fmt_axis(value: float) -> str:
    return _short(int(value))


def _short(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def _sum(values: list[int]) -> int:
    return sum(values)


def _grid(columns, n, height, keys, styles) -> list[Text]:
    rows: list[Text] = []
    for r in range(height - 1, -1, -1):
        line = Text()
        for i in range(n):
            column = columns[i]
            if r < len(column):
                key = column[r]
                line.append(BLOCK, style=styles.get(key, ""))
            else:
                line.append(" ")
        rows.append(line)
    return rows


def _x_labels(labels: list[str], offset: int, width: int) -> Text:
    """Place a few labels under the bars, anchored to the newest bucket.

    Anchoring at the right edge means the last label is always "now", which is
    the end a reader looks for. Labels are spaced at least as far apart as they
    are wide, so they can never run together.
    """
    line = [" "] * (offset + width)
    n = len(labels)
    if n == 0:
        return Text("".join(line))
    label_len = max(len(label) for label in labels)
    # width is the plot's character width, which is what decides how many
    # labels fit; the bars may be fewer than that.
    target = max(1, width // 8)
    step = max(1, -(-n // target), label_len + 1)
    for i in range(n - 1, -1, -step):
        label = labels[i][:5]
        # A label may hang one character past the last bar, never past the plot.
        start = min(offset + i, offset + width - len(label))
        for pos, ch in enumerate(label):
            if 0 <= start + pos < len(line):
                line[start + pos] = ch
    return Text("".join(line), style="grey37")
