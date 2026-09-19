import pytest

from mela_letterhead import i18n


class TestLanguageMapDetection:
    @pytest.mark.parametrize(
        "value",
        [
            {"en": "Reference"},
            {"en": "Reference", "it": "Codice"},
            {"pt-BR": "Referência"},
            {"de_AT": "Kennzeichen"},
        ],
    )
    def test_recognised(self, value):
        assert i18n.is_language_map(value)

    @pytest.mark.parametrize(
        "value",
        [
            {},
            {"label": "Reference", "value": "AQ-1"},
            {"width": "67mm", "y": "11mm"},
            {"show": True, "size": "8pt"},
            "Reference",
            ["en", "it"],
        ],
    )
    def test_not_recognised(self, value):
        assert not i18n.is_language_map(value)

    def test_record_keys_are_not_languages(self):
        # Inside a list the schema describes nothing, so shape is all there is
        # to go on, and a header field written with only a `key` in it must
        # still be a header field.
        assert not i18n.is_language_map({"key": "reference"})
        assert not i18n.is_language_map({"key": "date", "label": "Date"})


class TestIsTranslation:
    """Where a mapping was written decides what it is; its shape cannot."""

    MARGIN = {"x": "22mm", "top": "27.5mm", "bottom": "39.5mm"}

    def test_a_section_key_that_looks_like_a_tag_stays_a_key(self):
        # The defect this replaced: `top` is three letters, so a margin with
        # only a top set was read as Tok Pisin and swallowed the section.
        assert not i18n.is_translation({"top": "30mm"}, self.MARGIN)

    def test_a_section_borrowing_no_names_is_a_translation(self):
        tagline = {"text": None, "size": 0.055, "gap": "2.4mm"}
        assert i18n.is_translation({"en": "Surveying", "it": "Rilievi"}, tagline)

    def test_a_scalar_position_takes_a_translation(self):
        # `brand.logo` is a path in the schema, so a map there is per-market.
        assert i18n.is_translation({"en": "logo-en.svg", "it": "logo-it.svg"}, None)

    def test_an_unknown_position_falls_back_to_shape(self):
        assert i18n.is_translation({"en": "Date:", "de": "Datum:"})
        assert not i18n.is_translation({"key": "reference"})

    def test_a_mapping_that_is_no_language_map_never_is_one(self):
        assert not i18n.is_translation({"width": "67mm"}, None)


class TestFallbackChain:
    def test_region_falls_back_to_bare_language(self):
        assert i18n.fallback_chain("pt-BR", "it") == ["pt-BR", "pt", "it", "en"]

    def test_english_is_always_last(self):
        assert i18n.fallback_chain("de", "de")[-1] == "en"

    def test_no_duplicates(self):
        chain = i18n.fallback_chain("en", "en")
        assert chain == list(dict.fromkeys(chain))


class TestPick:
    def test_exact_match_wins(self):
        assert i18n.pick({"en": "Date", "it": "Data"}, ["it", "en"]) == "Data"

    def test_falls_through_to_the_next_language(self):
        assert i18n.pick({"en": "Date"}, ["de", "en"]) == "Date"

    def test_region_matches_its_bare_language(self):
        assert i18n.pick({"pt": "Data"}, ["pt-BR", "pt", "en"]) == "Data"

    def test_something_always_prints(self):
        # A label in the wrong language still prints; an empty one leaves a
        # hole in the page.
        assert i18n.pick({"fr": "Date"}, ["de", "en"]) == "Date"


class TestLocalise:
    def test_replaces_maps_anywhere_in_the_tree(self):
        source = {
            "header": {
                "items": [
                    {"label": {"en": "Type:", "it": "Tipologia:"}},
                    {"label": "Fixed"},
                ]
            },
            "size": "11pt",
        }
        result = i18n.localise(source, ["it", "en"])
        assert result["header"]["items"][0]["label"] == "Tipologia:"
        assert result["header"]["items"][1]["label"] == "Fixed"
        assert result["size"] == "11pt"

    def test_leaves_option_mappings_alone(self):
        source = {"logo": {"width": "67mm", "y": "11.8mm"}}
        assert i18n.localise(source, ["it", "en"]) == source

    def test_the_schema_protects_a_section_from_its_own_key_names(self):
        schema = {"page": {"margin": {"x": "22mm", "top": "27.5mm"}}}
        source = {"page": {"margin": {"top": "30mm"}}}
        assert i18n.localise(source, ["it", "en"], schema) == source

    def test_a_section_written_per_language_is_still_localised(self):
        schema = {"tagline": {"text": None, "gap": "2.4mm"}}
        source = {"tagline": {"en": {"text": "Surveying"}, "it": {"text": "Rilievi"}}}
        result = i18n.localise(source, ["it", "en"], schema)
        assert result["tagline"] == {"text": "Rilievi"}

    def test_a_record_inside_a_list_keeps_its_own_keys(self):
        # The schema says nothing about what a user puts in `items`, so the
        # record vocabulary is what keeps `key` from being read as a language.
        schema = {"items": []}
        source = {"items": [{"key": "reference"}]}
        assert i18n.localise(source, ["it", "en"], schema) == source


class TestSplitTag:
    @pytest.mark.parametrize(
        "tag, expected",
        [("en", ("en", None)), ("pt-BR", ("pt", "BR")), ("de_AT", ("de", "AT"))],
    )
    def test_splits_language_from_region(self, tag, expected):
        assert i18n.split_tag(tag) == expected


class TestLocalePacks:
    def test_english_ships_with_the_package(self):
        strings = i18n.load_locale(["en"])
        assert "{page}" in strings["running_header"]

    def test_a_project_pack_overrides_the_built_in_one(self, tmp_path):
        (tmp_path / "en.yaml").write_text("running_header: 'p. {page}'\n", encoding="utf-8")
        strings = i18n.load_locale(["en"], tmp_path)
        assert strings["running_header"] == "p. {page}"

    def test_a_new_language_needs_no_code(self, tmp_path):
        (tmp_path / "de.yaml").write_text(
            "running_header: '{title} · Seite {page} von {pages}'\n", encoding="utf-8"
        )
        strings = i18n.load_locale(["de", "en"], tmp_path)
        assert "Seite" in strings["running_header"]
        # Anything the new pack omits still falls back to English.
        assert strings["untitled"] == "Untitled document"

    def test_available_locales_lists_both_sources(self, tmp_path):
        (tmp_path / "de.yaml").write_text("untitled: x\n", encoding="utf-8")
        assert i18n.available_locales(tmp_path) == ["de", "en"]
