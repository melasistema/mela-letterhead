import pytest

from mela_letterhead import units
from mela_letterhead.errors import ConfigError


class TestToPoints:
    def test_bare_number_is_points(self):
        assert units.to_points(11, "x") == 11.0
        assert units.to_points("11", "x") == 11.0

    @pytest.mark.parametrize(
        "written, expected",
        [("1in", 72.0), ("72pt", 72.0), ("25.4mm", 72.0), ("2.54cm", 72.0), ("6pc", 72.0)],
    )
    def test_units_agree_on_an_inch(self, written, expected):
        assert units.to_points(written, "x") == pytest.approx(expected)

    def test_whitespace_and_case_are_forgiven(self):
        assert units.to_points("  22 MM ", "x") == pytest.approx(62.362, abs=1e-3)

    def test_a_boolean_is_not_a_length(self):
        # True is an int in Python; it must not silently become 1pt.
        with pytest.raises(ConfigError, match="boolean"):
            units.to_points(True, "header.height")

    def test_unknown_unit_names_the_field(self):
        with pytest.raises(ConfigError, match="header.height"):
            units.to_points("3 furlongs", "header.height")


class TestToEm:
    def test_bare_number_and_em_agree(self):
        assert units.to_em(0.82, "x") == 0.82
        assert units.to_em("0.82em", "x") == 0.82

    def test_absolute_units_are_refused(self):
        # A leading fixed in points stops tracking the text it sets.
        with pytest.raises(ConfigError, match="not a multiple"):
            units.to_em("9pt", "typography.leading")


class TestToRatio:
    def test_a_percentage_and_a_fraction_agree(self):
        assert units.to_ratio("60%", "x") == pytest.approx(0.6)
        assert units.to_ratio(0.6, "x") == pytest.approx(0.6)
        assert units.to_ratio("100%", "x") == pytest.approx(1.0)

    def test_a_bare_number_is_never_a_percentage(self):
        # `width: 60` means sixty times the column, which is a typo for 60%
        # every time. Refusing it here names the setting; letting it through
        # prints an image running off the page.
        with pytest.raises(ConfigError, match="images.width"):
            units.to_ratio(60, "images.width")

    @pytest.mark.parametrize("value", ["wide", "0%", -1, True, None])
    def test_rejected_forms(self, value):
        with pytest.raises(ConfigError, match="images.width"):
            units.to_ratio(value, "images.width")


class TestToColour:
    @pytest.mark.parametrize("value", ["#fff", "#f5f5f7", "#00000080"])
    def test_accepted_forms(self, value):
        assert units.to_colour(value, "palette.band") == value

    @pytest.mark.parametrize("value", ["fff", "#ff", "rebeccapurple", "#gggggg", 17])
    def test_rejected_forms(self, value):
        with pytest.raises(ConfigError, match="palette.band"):
            units.to_colour(value, "palette.band")


class TestPageSize:
    def test_a4_in_points(self):
        width, height = units.page_size("a4", "page.size")
        assert width == pytest.approx(595.28, abs=0.01)
        assert height == pytest.approx(841.89, abs=0.01)

    def test_landscape_swaps_the_axes(self):
        portrait = units.page_size("a4", "page.size")
        landscape = units.page_size("a4-landscape", "page.size")
        assert landscape == (portrait[1], portrait[0])

    def test_name_is_case_insensitive(self):
        assert units.page_size("Letter", "page.size") == units.page_size("letter", "page.size")

    def test_explicit_size(self):
        size = units.page_size({"width": "100mm", "height": "200mm"}, "page.size")
        assert size[0] == pytest.approx(283.46, abs=0.01)

    def test_explicit_size_needs_both_axes(self):
        with pytest.raises(ConfigError, match="height"):
            units.page_size({"width": "100mm"}, "page.size")

    def test_unknown_name_lists_the_known_ones(self):
        with pytest.raises(ConfigError) as caught:
            units.page_size("a4paper", "page.size")
        assert "letter" in caught.value.hint
