from mela_letterhead.markdown_prep import prepare

ALL_ON = {
    "rewrite_table_widths": True,
    "drop_horizontal_rules": True,
    "bold_table_header": True,
}

LAZY_TABLE = """\
| Item | Hours |
|---|---:|
| A very long description of the work carried out on site | 12 |
| Another long description of some further work | 6 |
"""


def separator_of(text):
    return next(line for line in text.splitlines() if set(line) <= set("|-: "))


def widths_of(separator):
    return [len(cell) for cell in separator.strip("|").split("|")]


class TestTableWidths:
    def test_columns_are_sized_by_their_content(self):
        # Pandoc reads a Typst column width from the dash count, so `|---|---:|`
        # would give "Hours" the same width as the description column.
        widths = widths_of(separator_of(prepare(LAZY_TABLE, ALL_ON)))
        assert widths[0] > widths[1]

    def test_alignment_markers_survive(self):
        separator = separator_of(prepare(LAZY_TABLE, ALL_ON))
        assert separator.strip("|").split("|")[1].endswith(":")
        assert not separator.strip("|").split("|")[0].endswith(":")

    def test_a_narrow_column_still_holds_its_longest_word(self):
        table = "| N | Description |\n|---|---|\n| 1 | " + "word " * 40 + "|\n"
        widths = widths_of(separator_of(prepare(table, ALL_ON)))
        assert widths[0] >= 3

    def test_an_unbreakable_word_widens_its_column(self):
        # No language hyphenates an IBAN; the column has to hold it outright.
        narrow = "| A | B |\n|---|---|\n| x | y |\n"
        wide = "| A | B |\n|---|---|\n| x | IT00X0000000000000000000000 |\n"
        assert widths_of(separator_of(prepare(wide, ALL_ON)))[1] > widths_of(
            separator_of(prepare(narrow, ALL_ON))
        )[1]

    def test_can_be_switched_off(self):
        options = dict(ALL_ON, rewrite_table_widths=False)
        assert "|---|---:|" in prepare(LAZY_TABLE, options)

    def test_a_table_without_a_separator_is_left_alone(self):
        text = "| just | pipes |\n| no | separator |\n"
        assert prepare(text, ALL_ON).strip() == text.strip()


class TestHeaderRow:
    def test_header_cells_are_emboldened(self):
        result = prepare(LAZY_TABLE, ALL_ON)
        assert "**Item**" in result and "**Hours**" in result

    def test_already_bold_cells_are_not_doubled(self):
        table = "| **Item** | Hours |\n|---|---|\n| a | 1 |\n"
        assert "****Item****" not in prepare(table, ALL_ON)

    def test_body_rows_are_untouched(self):
        result = prepare(LAZY_TABLE, ALL_ON)
        assert "**A very long description" not in result

    def test_can_be_switched_off(self):
        options = dict(ALL_ON, bold_table_header=False)
        assert "**Item**" not in prepare(LAZY_TABLE, options)


class TestHorizontalRules:
    def test_rules_are_dropped(self):
        result = prepare("One\n\n---\n\nTwo\n", ALL_ON)
        assert "---" not in result
        assert "One" in result and "Two" in result

    def test_can_be_switched_off(self):
        options = dict(ALL_ON, drop_horizontal_rules=False)
        assert "---" in prepare("One\n\n---\n\nTwo\n", options)


class TestFencedCode:
    def test_a_rule_inside_a_fence_is_content(self):
        text = "Before\n\n```\n---\n```\n\nAfter\n"
        assert "---" in prepare(text, ALL_ON)

    def test_a_table_inside_a_fence_is_not_rewritten(self):
        text = "```\n| a | b |\n|---|---:|\n```\n"
        assert "|---|---:|" in prepare(text, ALL_ON)

    def test_tilde_fences_work_too(self):
        text = "~~~\n---\n~~~\n"
        assert "---" in prepare(text, ALL_ON)

    def test_a_table_after_a_fence_is_still_rewritten(self):
        text = "```\ncode\n```\n\n" + LAZY_TABLE
        assert "|---|---:|" not in prepare(text, ALL_ON)


class TestWhitespace:
    def test_runs_of_blank_lines_collapse(self):
        assert "\n\n\n" not in prepare("One\n\n\n\n\nTwo\n", ALL_ON)
