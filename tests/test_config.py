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
        config = make_config(tmp_path, MINIMAL.replace("  fields:", "  fields:\n    when_empty: hide"))
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
