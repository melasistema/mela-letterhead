import pytest

from mela_letterhead import config as config_module
from mela_letterhead.document import Document
from mela_letterhead.errors import ConfigError

MINIMAL = """\
brand:
  name: Acme Studio
footer:
  columns:
    - title: { en: Acme Studio, it: Acme Studio }
      rows:
        - label: { en: "Office:", it: "Sede:" }
          value: 12 Example Street
        - ["Tel.", "+00 000"]
        - hello@acme.example
header:
  fields:
    items:
      - key: reference
        label: { en: "Reference:", it: "Codice:" }
      - key: date
        label: { en: "Date:", it: "Data:" }
"""


def make_config(tmp_path, text=MINIMAL):
    path = tmp_path / "letterhead.yaml"
    path.write_text(text, encoding="utf-8")
    return config_module.load(path)


def make_document(tmp_path, front_matter="reference: AQ-0184\nlang: it\n"):
    path = tmp_path / "doc.md"
    path.write_text(f"---\n{front_matter}---\n# Heading\n", encoding="utf-8")
    return Document.load(path)


class TestLoading:
    def test_defaults_fill_in_what_is_missing(self, tmp_path):
        config = make_config(tmp_path, "brand:\n  name: Acme\n")
        assert config.data["page"]["size"] == "a4"
        assert config.data["typography"]["size"] == "11pt"

    def test_an_empty_file_is_all_defaults(self, tmp_path):
        config = make_config(tmp_path, "")
        assert config.data["language"] == "en"

    def test_lists_replace_rather_than_extend(self, tmp_path):
        config = make_config(tmp_path, "documents:\n  exclude: ['NOTES.md']\n")
        assert config.data["documents"]["exclude"] == ["NOTES.md"]

    def test_a_section_key_shaped_like_a_language_is_merged_not_replaced(self, tmp_path):
        # `top` is three letters. Read as a language tag it made `page.margin`
        # the string "30mm", and resolving one raised TypeError out of Python
        # rather than a ConfigError naming the setting.
        config = make_config(tmp_path, "page:\n  margin:\n    top: 30mm\n")
        margin = config.data["page"]["margin"]
        assert margin["top"] == "30mm"
        assert margin["x"] == config_module.DEFAULT_CONFIG["page"]["margin"]["x"]
        assert margin["bottom"] == config_module.DEFAULT_CONFIG["page"]["margin"]["bottom"]

    @pytest.mark.parametrize(
        "written, section, key, expected",
        [
            ("page:\n  margin:\n    top: 30mm\n", ("page", "margin"), "top", "30mm"),
            ('header:\n  ink: "#0a0a0a"\n', ("header",), "ink", "#0a0a0a"),
            (
                "page:\n  background:\n    fit: contain\n",
                ("page", "background"),
                "fit",
                "contain",
            ),
            ("brand:\n  tagline:\n    gap: 4mm\n", ("brand", "tagline"), "gap", "4mm"),
        ],
    )
    def test_a_lone_short_key_never_swallows_its_section(
        self, tmp_path, written, section, key, expected
    ):
        data = make_config(tmp_path, written).data
        for name in section:
            data = data[name]
            assert isinstance(data, dict), "the section was read as a translation"
        assert data[key] == expected

    def test_an_unknown_key_is_named_and_a_fix_suggested(self, tmp_path):
        with pytest.raises(ConfigError) as caught:
            make_config(tmp_path, "palete:\n  band: '#fff'\n")
        assert "palete" in caught.value.message
        assert "palette" in caught.value.hint

    def test_an_unknown_nested_key_is_reported_with_its_path(self, tmp_path):
        with pytest.raises(ConfigError, match="header.heigth"):
            make_config(tmp_path, "header:\n  heigth: 40mm\n")

    def test_the_palette_is_validated_by_value_not_by_key(self, tmp_path):
        # Colours are checked when the configuration is resolved, not when the
        # file is read, so the message names the colour rather than the key.
        config = make_config(tmp_path, "palette:\n  band: not-a-colour\n")
        with pytest.raises(ConfigError, match="palette.band"):
            config_module.resolve(config, make_document(tmp_path), "en")

    def test_a_key_set_twice_is_named_with_both_its_lines(self, tmp_path):
        # The setting written at the top of a section, already set further
        # down: YAML takes the second and says nothing, so the page came out
        # 43mm and `check` called the file clean.
        with pytest.raises(ConfigError) as caught:
            make_config(tmp_path, "header:\n  height: 30mm\n  show: true\n  height: 43mm\n")
        assert "'height' is set twice" in caught.value.message
        assert "line 2" in caught.value.message
        assert "line 4" in caught.value.message
        assert "Delete whichever is not wanted" in caught.value.hint

    def test_a_future_schema_version_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="version"):
            make_config(tmp_path, "version: 99\n")

    def test_found_by_searching_upwards(self, tmp_path):
        (tmp_path / "letterhead.yaml").write_text(MINIMAL, encoding="utf-8")
        nested = tmp_path / "offers" / "2026"
        nested.mkdir(parents=True)
        assert config_module.find_config(nested) == tmp_path / "letterhead.yaml"

    def test_absent_config_says_how_to_make_one(self, tmp_path):
        with pytest.raises(ConfigError) as caught:
            config_module.load(start=tmp_path / "nowhere")
        assert "init" in caught.value.hint


class TestResolve:
    def test_lengths_become_points(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "en"
        )
        assert resolved["page"]["width"] == pytest.approx(595.28, abs=0.01)
        assert resolved["page"]["margin"]["x"] == pytest.approx(62.36, abs=0.01)

    def test_the_document_language_chooses_the_labels(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "it"
        )
        labels = [item["label"] for item in resolved["header"]["fields"]["items"]]
        assert labels == ["Codice:", "Data:"]

    def test_an_untranslated_language_falls_back(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "de"
        )
        assert resolved["header"]["fields"]["items"][0]["label"] == "Reference:"

    def test_field_values_come_from_the_document(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "en"
        )
        by_label = {i["label"]: i["value"] for i in resolved["header"]["fields"]["items"]}
        assert by_label["Reference:"] == "AQ-0184"
        # A field the document does not set becomes a line to fill in by hand.
        assert by_label["Date:"] is None

    def test_when_empty_hide_drops_the_field(self, tmp_path):
        written = MINIMAL.replace("  fields:", "  fields:\n    when_empty: hide")
        config = make_config(tmp_path, written)
        resolved = config_module.resolve(config, make_document(tmp_path), "en")
        assert len(resolved["header"]["fields"]["items"]) == 1

    def test_lang_and_region_are_split_for_typst(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "pt-BR"
        )
        assert resolved["document"]["lang"] == "pt"
        assert resolved["document"]["region"] == "BR"

    def test_the_first_page_is_pushed_below_the_header_band(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "en"
        )
        header = resolved["header"]
        expected = header["height"] + header["gap"] - resolved["page"]["margin"]["top"]
        assert resolved["page"]["first_page_extra"] == pytest.approx(expected)

    def test_a_footer_on_every_page_is_reserved_in_the_margin(self, tmp_path):
        config = make_config(
            tmp_path, MINIMAL.replace("footer:\n", "footer:\n  pages: all\n")
        )
        resolved = config_module.resolve(config, make_document(tmp_path), "en")
        footer = resolved["footer"]
        assert resolved["page"]["margin"]["bottom"] >= footer["height"] + footer["gap"]
        assert resolved["page"]["footer_reserve"] == 0

    def test_a_footer_on_the_last_page_is_reserved_in_the_body(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "en"
        )
        assert resolved["page"]["footer_reserve"] > 0

    def test_page_placeholders_are_left_for_typst(self, tmp_path):
        # {title} is known now; {page} is not known until the pages exist.
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "en"
        )
        assert "{page}" in resolved["running"]["text"]
        assert "{title}" not in resolved["running"]["text"]
        assert "Heading" in resolved["running"]["text"]


class TestImages:
    def _images(self, tmp_path, text=MINIMAL):
        resolved = config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), "en"
        )
        return resolved["images"]

    def test_auto_is_no_width_at_all(self, tmp_path):
        # Not 100%: an image with no width of its own keeps its natural size,
        # which is not the same as one filling the column.
        assert self._images(tmp_path)["width"] is None

    def test_a_share_becomes_a_fraction(self, tmp_path):
        images = self._images(tmp_path, MINIMAL + "images:\n  width: 70%\n")
        assert images["width"] == pytest.approx(0.7)

    def test_the_caption_is_measured_in_points(self, tmp_path):
        images = self._images(tmp_path, MINIMAL + "images:\n  caption:\n    gap: 1in\n")
        assert images["caption"]["gap"] == pytest.approx(72.0)

    def test_an_alignment_that_is_not_one_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="images.align"):
            self._images(tmp_path, MINIMAL + "images:\n  align: middle\n")


class TestBandColours:
    """A band is recoloured on its own, or follows the palette."""

    def _resolve(self, tmp_path, text=MINIMAL):
        return config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), "en"
        )

    def test_a_band_follows_the_palette_by_default(self, tmp_path):
        resolved = self._resolve(tmp_path)
        palette = resolved["palette"]
        assert resolved["header"]["fill"] == palette["band"]
        assert resolved["footer"]["ink"] == palette["ink"]
        assert resolved["footer"]["rule_color"] == palette["rule"]

    def test_a_band_may_be_coloured_without_the_quotations_going_with_it(self, tmp_path):
        # The whole point of the setting: `palette.band` also fills the block
        # quotations and the code, so a strongly coloured header must not be
        # written there.
        resolved = self._resolve(
            tmp_path, MINIMAL.replace("header:\n", 'header:\n  fill: "#2b2440"\n  ink: "#f3f1fa"\n')
        )
        assert resolved["header"]["fill"] == "#2b2440"
        assert resolved["header"]["ink"] == "#f3f1fa"
        assert resolved["palette"]["band"] == "#f5f5f7"

    def test_the_two_bands_are_coloured_apart(self, tmp_path):
        written = MINIMAL.replace("footer:\n", 'footer:\n  fill: "#101014"\n')
        resolved = self._resolve(tmp_path, written)
        assert resolved["footer"]["fill"] == "#101014"
        assert resolved["header"]["fill"] == resolved["palette"]["band"]

    def test_a_colour_that_is_not_one_names_the_setting(self, tmp_path):
        with pytest.raises(ConfigError, match="header.fill"):
            self._resolve(tmp_path, MINIMAL.replace("header:\n", "header:\n  fill: dark purple\n"))

    def test_ink_is_a_setting_and_not_a_language(self, tmp_path):
        # `ink` has the shape of a language tag, and a section holding nothing
        # else would be read as a translation without the reserved-key list.
        written = MINIMAL.replace("header:\n", 'header:\n  ink: "#0a0a0a"\n')
        resolved = self._resolve(tmp_path, written)
        assert resolved["header"]["ink"] == "#0a0a0a"
        assert resolved["header"]["fields"]["items"], "the section was swallowed"


class TestWordmark:
    """The brand name set in type, for a letterhead with no logo file."""

    def _brand(self, tmp_path, text=MINIMAL, language="en"):
        resolved = config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), language
        )
        return resolved["brand"]

    def test_the_parts_are_shares_of_the_mark(self, tmp_path):
        # So that the smaller mark in the running header is the same design.
        wordmark = self._brand(tmp_path)["wordmark"]
        assert wordmark["size"] == pytest.approx(0.17)
        assert wordmark["font"] == ["Libertinus Serif", "New Computer Modern"]

    def test_a_length_is_read_as_a_share_of_the_slot(self, tmp_path):
        # 67mm is `header.logo.width`, so 34pt is a little over a sixth of it.
        written = MINIMAL.replace("brand:\n", "brand:\n  wordmark:\n    size: 34pt\n")
        wordmark = self._brand(tmp_path, written)
        assert wordmark["wordmark"]["size"] == pytest.approx(34 / (67 * 72 / 25.4))

    def test_tracking_may_be_nothing_at_all(self, tmp_path):
        wordmark = self._brand(
            tmp_path, MINIMAL.replace("brand:\n", "brand:\n  wordmark:\n    tracking: 0\n")
        )
        assert wordmark["wordmark"]["tracking"] == 0

    def test_the_mark_is_coloured_for_both_grounds(self, tmp_path):
        # Pale on a dark band, and still legible on the bare paper of the
        # running header, which has no band behind it.
        brand = self._brand(
            tmp_path, MINIMAL.replace("header:\n", 'header:\n  fill: "#2b2440"\n  ink: "#f3f1fa"\n')
        )
        assert brand["wordmark"]["color"] == "#f3f1fa"
        assert brand["wordmark"]["running_color"] == "#1c1c20"

    def test_a_colour_of_its_own_is_used_in_both_places(self, tmp_path):
        written = MINIMAL.replace("brand:\n", 'brand:\n  wordmark:\n    color: "#c00"\n')
        brand = self._brand(tmp_path, written)
        assert brand["wordmark"]["color"] == "#c00"
        assert brand["wordmark"]["running_color"] == "#c00"

    def test_a_weight_outside_the_scale_is_refused(self, tmp_path):
        written = MINIMAL.replace("brand:\n", "brand:\n  wordmark:\n    weight: 1200\n")
        with pytest.raises(ConfigError, match="brand.wordmark.weight"):
            self._brand(tmp_path, written)

    def test_a_named_weight_is_passed_through(self, tmp_path):
        brand = self._brand(
            tmp_path, MINIMAL.replace("brand:\n", "brand:\n  wordmark:\n    weight: semibold\n")
        )
        assert brand["wordmark"]["weight"] == "semibold"


class TestTagline:
    def _tagline(self, tmp_path, text, language="en"):
        resolved = config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), language
        )
        return resolved["brand"]["tagline"]

    def test_there_is_none_by_default(self, tmp_path):
        assert self._tagline(tmp_path, MINIMAL)["text"] is None

    def test_a_plain_string_is_the_text(self, tmp_path):
        written = MINIMAL.replace("brand:\n", "brand:\n  tagline: Graphic design\n")
        tagline = self._tagline(tmp_path, written)
        assert tagline["text"] == "Graphic design"
        assert tagline["gap"] == pytest.approx(2.4 * 72 / 25.4)

    def test_it_may_be_written_per_language(self, tmp_path):
        text = MINIMAL.replace("brand:\n", "brand:\n  tagline: { en: Surveying, it: Rilievi }\n")
        assert self._tagline(tmp_path, text, "it")["text"] == "Rilievi"

    def test_the_full_form_styles_it(self, tmp_path):
        text = MINIMAL.replace(
            "brand:\n",
            "brand:\n"
            "  tagline:\n"
            "    text: { en: Surveying, it: Rilievi }\n"
            "    size: 11pt\n"
            '    color: "#445"\n',
        )
        tagline = self._tagline(tmp_path, text, "it")
        assert tagline["text"] == "Rilievi"
        assert tagline["color"] == "#445"
        assert tagline["size"] == pytest.approx(11 / (67 * 72 / 25.4))

    def test_it_follows_the_header_band(self, tmp_path):
        text = MINIMAL.replace("brand:\n", "brand:\n  tagline: Surveying\n").replace(
            "header:\n", 'header:\n  muted: "#9d95bd"\n'
        )
        assert self._tagline(tmp_path, text)["color"] == "#9d95bd"

    def test_an_empty_one_is_no_tagline(self, tmp_path):
        written = MINIMAL.replace("brand:\n", "brand:\n  tagline: '   '\n")
        assert self._tagline(tmp_path, written)["text"] is None


class TestBorder:
    def _border(self, tmp_path, text=MINIMAL):
        resolved = config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), "en"
        )
        return resolved["page"]["border"]

    def test_there_is_none_by_default(self, tmp_path):
        assert self._border(tmp_path)["width"] == 0

    def test_one_side_is_drawn_and_the_others_are_not(self, tmp_path):
        border = self._border(
            tmp_path, MINIMAL + "page:\n  border:\n    width: 2.4pt\n    sides: left\n"
        )
        assert border["width"] == pytest.approx(2.4)
        assert border["sides"] == {
            "left": True,
            "right": False,
            "top": False,
            "bottom": False,
        }

    def test_sides_may_be_a_list(self, tmp_path):
        border = self._border(
            tmp_path, MINIMAL + "page:\n  border:\n    sides: [left, bottom]\n"
        )
        assert border["sides"]["left"] and border["sides"]["bottom"]
        assert not border["sides"]["top"]

    def test_it_falls_back_to_the_accent_colour(self, tmp_path):
        assert self._border(tmp_path)["color"] == "#4a3f8a"

    def test_a_side_that_is_not_one_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="page.border.sides"):
            self._border(tmp_path, MINIMAL + "page:\n  border:\n    sides: diagonal\n")


class TestBackground:
    def _background(self, tmp_path, text=MINIMAL):
        resolved = config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), "en"
        )
        return resolved["page"]["background"]

    def _written(self, settings):
        return MINIMAL + "page:\n  background:\n" + settings

    def test_there_is_none_by_default(self, tmp_path):
        background = self._background(tmp_path)
        assert background["image"] is None
        assert background["veil"] == 0

    def test_the_written_path_travels_for_the_builder_to_replace(self, tmp_path):
        background = self._background(
            tmp_path, self._written("    image: assets/sheet.png\n")
        )
        assert background["image"] == "assets/sheet.png"
        assert background["fit"] == "cover"
        assert background["pages"] == "first"

    def test_a_sheet_may_be_written_once_per_language(self, tmp_path):
        # A designer with an Italian sheet and an English one is the ordinary
        # case, not an exotic one.
        text = self._written(
            "    image: { en: assets/sheet-en.png, it: assets/sheet-it.png }\n"
        )
        config = make_config(tmp_path, text)
        italian = config_module.resolve(config, make_document(tmp_path), "it")
        assert italian["page"]["background"]["image"] == "assets/sheet-it.png"
        english = config_module.resolve(config, make_document(tmp_path), "en")
        assert english["page"]["background"]["image"] == "assets/sheet-en.png"

    @pytest.mark.parametrize("written", ["35%", "0.35"])
    def test_the_veil_is_a_share_however_it_is_written(self, tmp_path, written):
        background = self._background(tmp_path, self._written(f"    veil: {written}\n"))
        assert background["veil"] == pytest.approx(0.35)

    def test_a_veil_thicker_than_opaque_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="page.background.veil"):
            self._background(tmp_path, self._written("    veil: 35\n"))

    def test_fit_is_a_setting_and_not_a_language(self, tmp_path):
        # `fit` has the shape of a language tag, so a background written with
        # nothing else in it would otherwise be read as a translation and
        # swallow the section.
        background = self._background(tmp_path, self._written("    fit: contain\n"))
        assert background["fit"] == "contain"

    def test_a_fit_typst_has_no_name_for_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="page.background.fit"):
            self._background(tmp_path, self._written("    fit: stretch\n"))

    def test_the_pages_it_prints_on(self, tmp_path):
        background = self._background(tmp_path, self._written("    pages: rest\n"))
        assert background["pages"] == "rest"

    def test_the_footers_spelling_is_not_this_ones(self, tmp_path):
        # `footer.pages` takes last/all and this one first/rest/all, so the
        # wrong one has to be named rather than quietly meaning "first".
        with pytest.raises(ConfigError, match="page.background.pages"):
            self._background(tmp_path, self._written("    pages: last\n"))


class TestFooterRows:
    def _rows(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "en"
        )
        return resolved["footer"]["columns"][0]["rows"]

    def test_the_three_shorthands(self, tmp_path):
        rows = self._rows(tmp_path)
        assert rows[0] == {
            "label": "Office:",
            "value": "12 Example Street",
            "link": None,
            "style": "normal",
        }
        assert rows[1]["label"] == "Tel." and rows[1]["value"] == "+00 000"
        assert rows[2]["label"] is None and rows[2]["value"] == "hello@acme.example"

    def test_an_address_gets_its_mailto_for_free(self, tmp_path):
        assert self._rows(tmp_path)[2]["link"] == "mailto:hello@acme.example"

    def test_a_pair_of_the_wrong_length_says_what_to_write(self, tmp_path):
        text = MINIMAL.replace('- ["Tel.", "+00 000"]', '- ["Tel.", "a", "b"]')
        with pytest.raises(ConfigError) as caught:
            config_module.resolve(make_config(tmp_path, text), make_document(tmp_path), "en")
        assert "label:" in caught.value.hint

    def test_an_unknown_style_is_refused(self, tmp_path):
        text = MINIMAL.replace(
            "          value: 12 Example Street",
            "          value: 12 Example Street\n          style: flashing",
        )
        with pytest.raises(ConfigError, match="style"):
            config_module.resolve(make_config(tmp_path, text), make_document(tmp_path), "en")


class TestPdfStandard:
    def _resolve(self, tmp_path, written):
        text = MINIMAL + f"pdf:\n  standard: {written}\n"
        return config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), "en"
        )

    def test_nothing_asked_for_is_the_default(self, tmp_path):
        resolved = config_module.resolve(
            make_config(tmp_path), make_document(tmp_path), "en"
        )
        assert resolved["pdf"]["standard"] == []

    def test_one_name_on_its_own(self, tmp_path):
        assert self._resolve(tmp_path, "a-3b")["pdf"]["standard"] == ["a-3b"]

    def test_a_list_keeps_the_order_it_was_written_in(self, tmp_path):
        resolved = self._resolve(tmp_path, "[ua-1, a-3b]")
        assert resolved["pdf"]["standard"] == ["ua-1", "a-3b"]

    def test_a_name_is_read_however_it_is_cased(self, tmp_path):
        assert self._resolve(tmp_path, "[A-3B]")["pdf"]["standard"] == ["a-3b"]

    def test_the_same_name_twice_is_the_same_request(self, tmp_path):
        assert self._resolve(tmp_path, "[a-3b, a-3b]")["pdf"]["standard"] == ["a-3b"]

    def test_an_unknown_name_is_refused_with_the_nearest_one(self, tmp_path):
        with pytest.raises(ConfigError, match="pdf.standard") as caught:
            self._resolve(tmp_path, "a2b")
        assert "a-2b" in caught.value.hint

    def test_something_that_is_not_a_name_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="pdf.standard"):
            self._resolve(tmp_path, "[3]")

    # Which combinations are legal is Typst's to answer, not this module's, so
    # an impossible pair resolves here and is refused at the compile.
    def test_an_impossible_pair_still_resolves(self, tmp_path):
        assert self._resolve(tmp_path, "[a-4, ua-1]")["pdf"]["standard"] == [
            "a-4",
            "ua-1",
        ]


class TestFooterLinksUnderUa1:
    def _rows(self, tmp_path, standard="[]"):
        text = MINIMAL + f"pdf:\n  standard: {standard}\n"
        resolved = config_module.resolve(
            make_config(tmp_path, text), make_document(tmp_path), "en"
        )
        return resolved["footer"]["columns"][0]["rows"]

    def test_a_target_survives_an_archival_standard(self, tmp_path):
        assert self._rows(tmp_path, "a-3b")[2]["link"] == "mailto:hello@acme.example"

    def test_ua_1_drops_the_target_and_keeps_the_text(self, tmp_path):
        row = self._rows(tmp_path, "ua-1")[2]
        assert row["link"] is None
        assert row["value"] == "hello@acme.example"

    def test_a_target_written_by_hand_goes_too(self, tmp_path):
        text = MINIMAL.replace(
            "        - hello@acme.example",
            "        - label: Web\n          value: acme.example\n"
            "          link: https://acme.example",
        )
        resolved = config_module.resolve(
            make_config(tmp_path, text + "pdf:\n  standard: [a-2b, ua-1]\n"),
            make_document(tmp_path),
            "en",
        )
        row = resolved["footer"]["columns"][0]["rows"][2]
        assert row["link"] is None and row["value"] == "acme.example"


class TestValidation:
    def test_footer_pages_takes_only_last_or_all(self, tmp_path):
        config = make_config(
            tmp_path, MINIMAL.replace("footer:\n", "footer:\n  pages: sometimes\n")
        )
        with pytest.raises(ConfigError, match="footer.pages"):
            config_module.resolve(config, make_document(tmp_path), "en")

    def test_an_alignment_must_be_one_of_three(self, tmp_path):
        config = make_config(tmp_path, MINIMAL + "running:\n  align: middle\n")
        with pytest.raises(ConfigError, match="running.align"):
            config_module.resolve(config, make_document(tmp_path), "en")

    def test_a_font_stack_may_be_a_single_name(self, tmp_path):
        config = make_config(tmp_path, "fonts:\n  serif: Georgia\n")
        resolved = config_module.resolve(config, make_document(tmp_path), "en")
        assert resolved["fonts"]["serif"] == ["Georgia"]

    def test_display_defaults_to_the_serif_stack(self, tmp_path):
        config = make_config(tmp_path, "fonts:\n  serif: [Georgia]\n")
        resolved = config_module.resolve(config, make_document(tmp_path), "en")
        assert resolved["fonts"]["display"] == ["Georgia"]

    def test_an_empty_font_stack_is_refused(self, tmp_path):
        config = make_config(tmp_path, "fonts:\n  serif: []\n")
        with pytest.raises(ConfigError, match="empty"):
            config_module.resolve(config, make_document(tmp_path), "en")

    def test_a_footer_with_no_columns_is_not_drawn(self, tmp_path):
        config = make_config(tmp_path, "brand:\n  name: Acme\n")
        resolved = config_module.resolve(config, make_document(tmp_path), "en")
        assert resolved["footer"]["show"] is False
        assert resolved["page"]["footer_reserve"] == 0


PROFILED = MINIMAL + """\
profiles:
  draft:
    palette:
      accent: "#a4262c"
  final:
    palette:
      accent: "#000000"
"""


class TestProfiles:
    """Two of the three sources the written shape now has.

    A profile is a named set of overrides in `letterhead.yaml`; a document's
    own `letterhead:` block is the third, and beats it. Both are merged in
    `resolve`, which is the one function `check` and `build` share.
    """

    def test_a_profile_is_not_a_setting(self, tmp_path):
        # Popped before the merge, so it never reaches `data` and never has to
        # be exempted from anything downstream.
        config = make_config(tmp_path, PROFILED)
        assert "profiles" not in config.data
        assert sorted(config.profiles) == ["draft", "final"]

    def test_it_changes_what_it_names_and_leaves_the_rest(self, tmp_path):
        config = make_config(tmp_path, PROFILED)
        resolved = config_module.resolve(
            config, make_document(tmp_path), "en", "draft"
        )
        assert resolved["palette"]["accent"] == "#a4262c"
        # The rest of the palette is still the palette.
        assert resolved["palette"]["ink"] == config_module.DEFAULT_CONFIG["palette"]["ink"]

    def test_nothing_asked_for_changes_nothing(self, tmp_path):
        config = make_config(tmp_path, PROFILED)
        plain = config_module.resolve(config, make_document(tmp_path), "en")
        assert plain["palette"]["accent"] == config_module.DEFAULT_CONFIG["palette"]["accent"]

    def test_a_profile_named_like_a_language_survives(self, tmp_path):
        # The trap that makes popping `profiles` non-negotiable rather than
        # merely tidy: with an empty schema node `is_translation` falls through
        # to shape alone, so `profiles: { de:, it: }` would be read as a
        # translation *of* `profiles` and collapsed to one of them.
        config = make_config(
            tmp_path,
            MINIMAL + 'profiles:\n  de:\n    palette:\n      accent: "#111111"\n'
            '  it:\n    palette:\n      accent: "#222222"\n',
        )
        assert sorted(config.profiles) == ["de", "it"]
        resolved = config_module.resolve(config, make_document(tmp_path), "it", "de")
        assert resolved["palette"]["accent"] == "#111111"

    def test_an_unknown_setting_inside_one_names_the_profile(self, tmp_path):
        config = make_config(
            tmp_path, MINIMAL + "profiles:\n  draft:\n    palete:\n      accent: '#000'\n"
        )
        with pytest.raises(ConfigError, match=r"profiles\.draft\.palete"):
            config_module.resolve(config, make_document(tmp_path), "en", "draft")

    def test_an_unknown_profile_is_refused_with_a_suggestion(self, tmp_path):
        # Silently ignoring `--profile finl` is how a draft reaches a client.
        config = make_config(tmp_path, PROFILED)
        with pytest.raises(ConfigError, match="unknown profile") as caught:
            config_module.resolve(config, make_document(tmp_path), "en", "finl")
        assert "final" in caught.value.hint

    def test_an_unknown_profile_where_none_are_defined_says_so(self, tmp_path):
        config = make_config(tmp_path, MINIMAL)
        with pytest.raises(ConfigError) as caught:
            config_module.resolve(config, make_document(tmp_path), "en", "draft")
        assert "No profiles are defined" in caught.value.hint

    def test_a_profile_that_is_not_a_mapping_is_refused_at_load(self, tmp_path):
        with pytest.raises(ConfigError, match="profiles.draft"):
            make_config(tmp_path, MINIMAL + "profiles:\n  draft: watermark\n")

    def test_profiles_that_are_not_a_mapping_at_all_are_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="profiles"):
            make_config(tmp_path, MINIMAL + "profiles: [draft, final]\n")


class TestDocumentOverrides:
    def test_the_front_matter_block_changes_this_document_alone(self, tmp_path):
        config = make_config(tmp_path, MINIMAL)
        document = make_document(
            tmp_path,
            "lang: en\nletterhead:\n  palette:\n    accent: '#a4262c'\n",
        )
        resolved = config_module.resolve(config, document, "en")
        assert resolved["palette"]["accent"] == "#a4262c"
        # And nothing about the configuration it was merged onto.
        assert config.data["palette"]["accent"] == "#4a3f8a"

    def test_it_beats_the_profile(self, tmp_path):
        config = make_config(tmp_path, PROFILED)
        document = make_document(
            tmp_path,
            "lang: en\nletterhead:\n  palette:\n    accent: '#00ff00'\n",
        )
        resolved = config_module.resolve(config, document, "en", "draft")
        assert resolved["palette"]["accent"] == "#00ff00"

    def test_a_document_may_name_its_own_profile(self, tmp_path):
        config = make_config(tmp_path, PROFILED)
        document = make_document(tmp_path, "lang: en\nprofile: draft\n")
        resolved = config_module.resolve(config, document, "en")
        assert resolved["palette"]["accent"] == "#a4262c"

    def test_the_flag_beats_the_front_matter(self, tmp_path):
        # `build --profile final` is a thing you typed one second ago about
        # this run; a per-document veto would break the one use it has.
        config = make_config(tmp_path, PROFILED)
        document = make_document(tmp_path, "lang: en\nprofile: draft\n")
        resolved = config_module.resolve(config, document, "en", "final")
        assert resolved["palette"]["accent"] == "#000000"

    def test_an_unknown_setting_in_the_block_names_the_block(self, tmp_path):
        config = make_config(tmp_path, MINIMAL)
        document = make_document(tmp_path, "lang: en\nletterhead:\n  palete: {}\n")
        with pytest.raises(ConfigError, match=r"letterhead\.palete"):
            config_module.resolve(config, document, "en")

    def test_a_block_that_is_not_a_mapping_is_refused_by_name(self, tmp_path):
        from mela_letterhead.errors import DocumentError

        config = make_config(tmp_path, MINIMAL)
        document = make_document(tmp_path, "lang: en\nletterhead: nothing\n")
        with pytest.raises(DocumentError, match="letterhead"):
            config_module.resolve(config, document, "en")

    def test_neither_key_is_the_user_s(self, tmp_path):
        # Front matter is the user's except for what `RESERVED_KEYS` names,
        # and a header field printing `letterhead` would stringify a whole
        # mapping of settings onto the page.
        from mela_letterhead import document as document_module

        assert "letterhead" in document_module.RESERVED_KEYS
        assert "profile" in document_module.RESERVED_KEYS

    def test_a_translated_override_still_resolves_per_language(self, tmp_path):
        # The merge-order test. Localise before merging and this is impossible:
        # the override has to reach `localise` as a language map rather than as
        # a string somebody already chose.
        config = make_config(tmp_path, MINIMAL)
        front_matter = (
            "lang: it\nletterhead:\n  brand:\n"
            "    tagline: { en: 'Surveys', it: 'Perizie' }\n"
        )
        document = make_document(tmp_path, front_matter)

        def tagline(language):
            return config_module.resolve(config, document, language)["brand"]["tagline"]

        assert tagline("it")["text"] == "Perizie"
        assert tagline("en")["text"] == "Surveys"


class TestCountingOverrides:
    """What `check` prints, which is the only thing that makes an override
    visible before the PDF is opened."""

    def test_a_section_counts_the_settings_in_it(self):
        assert config_module.count_settings(
            {"palette": {"accent": "#000", "ink": "#111"}, "footer": {"show": False}}
        ) == 3

    def test_a_translation_counts_as_the_one_setting_it_translates(self):
        assert config_module.count_settings(
            {"brand": {"tagline": {"en": "Surveys", "it": "Perizie"}}}
        ) == 1

    def test_nothing_is_nothing(self):
        assert config_module.count_settings({}) == 0
