"""Preparing Markdown for typesetting.

These are layout transformations, not content ones: the source file is never
modified, and nothing here changes what the document says.

**Table widths.** Pandoc derives the width of a Typst table column from the
number of dashes in the Markdown separator row. That is a reasonable reading of
a hand-aligned table and a terrible one of a lazily written ``|---|---:|``,
which gives every column an equal share regardless of what is in it — a column
holding the word "Hours" ends up as wide as one holding a sentence. The
separator row is rewritten with a dash count proportional to the content each
column actually carries, alignment markers preserved.

**Horizontal rules.** ``---`` between sections is a writing convention; on paper
the hierarchy is already carried by the rules above headings, and a full-width
line on top of that reads as heavy.

**Header rows.** The header row of a table is set in bold, which distinguishes
it without a Typst rule on the first row — such a rule would also catch the
tables that have no header at all.

Each transformation can be switched off in ``letterhead.yaml``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

#: A table separator row: ``|---|:--:|---:|``
_SEPARATOR_RE = re.compile(r"^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$")

#: A horizontal rule on a line of its own.
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")

#: The opening or closing line of a fenced code block.
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

#: Inline markup that occupies no width on paper. Underscores are left alone:
#: in a placeholder such as ``[ ______ ]`` they are the content.
_MARKUP_RE = re.compile(r"[*`]")

#: Dashes distributed across the whole separator row. The absolute number does
#: not matter — Pandoc reads the proportions — but a large total keeps the
#: rounding error of a narrow column small.
_TOTAL_WIDTH = 120

#: No column is narrowed below this, whatever the arithmetic says.
_MINIMUM = 9

#: Below 1, so that a column with ten times the text is not ten times as wide.
_DAMPING = 0.7


def prepare(text: str, options: dict[str, object] | None = None) -> str:
    """Apply the enabled transformations to a Markdown body."""
    options = options or {}
    rewrite_tables = bool(options.get("rewrite_table_widths", True))
    drop_rules = bool(options.get("drop_horizontal_rules", True))
    bold_header = bool(options.get("bold_table_header", True))

    lines = text.split("\n")
    output: list[str] = []
    table: list[str] = []
    fence: str = ""

    def flush_table() -> None:
        if table:
            output.extend(_rewrite_table(table, rewrite_tables, bold_header))
            table.clear()

    for line in lines:
        # Inside a fenced block everything is content, including lines that
        # look like tables and rules.
        if fence:
            output.append(line)
            if line.strip().startswith(fence):
                fence = ""
            continue

        fence_start = _FENCE_RE.match(line)
        if fence_start:
            flush_table()
            fence = fence_start.group(1)
            output.append(line)
            continue

        if line.lstrip().startswith("|"):
            table.append(line)
            continue

        flush_table()

        if drop_rules and _RULE_RE.match(line):
            continue

        output.append(line)

    flush_table()
    return _collapse_blank_lines(output)


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------


def _rewrite_table(block: list[str], rewrite_widths: bool, bold_header: bool) -> list[str]:
    """Rewrite one pipe table's separator row and header row."""
    separator_index = next(
        (i for i, line in enumerate(block) if _SEPARATOR_RE.match(line)), None
    )
    if separator_index is None:
        return list(block)

    separator = _cells(block[separator_index])
    column_count = len(separator)
    body = [_cells(line) for i, line in enumerate(block) if i != separator_index]
    body = [row for row in body if len(row) == column_count]
    if not body:
        return list(block)

    result = list(block)

    if rewrite_widths:
        widths = _column_widths(body, column_count)
        rebuilt = "|"
        for index in range(column_count):
            left, right = _alignment(separator[index])
            rebuilt += _dashes(widths[index], left, right) + "|"
        result[separator_index] = rebuilt

    if bold_header and separator_index > 0:
        header = _cells(block[separator_index - 1])
        if len(header) == column_count and any(cell for cell in header):
            result[separator_index - 1] = (
                "| " + " | ".join(_embolden(cell) for cell in header) + " |"
            )

    return result


def _column_widths(rows: Sequence[Sequence[str]], column_count: int) -> list[int]:
    """Share ``_TOTAL_WIDTH`` dashes out between the columns."""
    weights: list[float] = []
    minimums: list[float] = []

    for index in range(column_count):
        column = [row[index] for row in rows]
        lengths = [len(_bare(cell)) for cell in column]
        mean = sum(lengths) / len(lengths)
        longest = max(lengths)
        # The mean governs the width and the longest cell corrects it upwards;
        # damping stops one verbose column from taking the page.
        weights.append(max(4.0, 0.6 * mean + 0.4 * longest) ** _DAMPING)
        # A word is not always breakable — Italian hyphenation will not cross
        # the apostrophe in "dell'affidamento", and no language breaks an IBAN
        # — so a column has to be able to hold its longest word outright.
        minimums.append(max(_MINIMUM, 3 + _longest_word(column) * 1.15))

    total = sum(weights)
    shares = [weight / total * _TOTAL_WIDTH for weight in weights]

    # Raise the columns that fell below their minimum, taking the difference
    # from those above theirs in proportion. Three passes settle any table with
    # a plausible number of columns.
    #
    # `strict` throughout: both lists hold one entry per column and are paired
    # by position, so a length that has drifted is a bug rather than a shorter
    # loop. Silently, it would cost the last column its width.
    for _ in range(3):
        debt = sum(
            low - share for share, low in zip(shares, minimums, strict=True) if share < low
        )
        if debt <= 0:
            break
        slack = sum(
            share - low for share, low in zip(shares, minimums, strict=True) if share > low
        )
        if slack <= 0:
            break
        factor = min(1.0, debt / slack)
        shares = [
            low if share < low else share - (share - low) * factor
            for share, low in zip(shares, minimums, strict=True)
        ]

    return [max(3, round(share)) for share in shares]


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _alignment(cell: str) -> tuple[bool, bool]:
    stripped = cell.strip()
    return stripped.startswith(":"), stripped.endswith(":")


def _dashes(count: int, left: bool, right: bool) -> str:
    count = max(count, 3 + int(left) + int(right))
    body = "-" * (count - int(left) - int(right))
    return (":" if left else "") + body + (":" if right else "")


def _bare(text: str) -> str:
    """The length a cell occupies once the markup that does not print is gone."""
    return _MARKUP_RE.sub("", text)


def _longest_word(cells: Sequence[str]) -> int:
    return max(
        (len(word) for cell in cells for word in _bare(cell).split()),
        default=1,
    )


def _embolden(cell: str) -> str:
    if not cell or cell.startswith("**"):
        return cell
    return f"**{cell}**"


def _collapse_blank_lines(lines: Sequence[str]) -> str:
    """Reduce runs of blank lines to one. Pandoc treats any run alike."""
    collapsed: list[str] = []
    for line in lines:
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)
    return "\n".join(collapsed)
