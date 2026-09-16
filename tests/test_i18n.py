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

    def test_reserved_keys_are_not_languages(self):
        # `on: last` was a footer setting before the key was renamed; a mapping
        # made only of such words must never be read as a translation.
        assert not i18n.is_language_map({"on": "last"})


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
