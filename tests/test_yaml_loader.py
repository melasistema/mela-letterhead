import pytest
import yaml

from mela_letterhead import yaml_loader


class TestDuplicateKeys:
    """The last of two keys spelled the same way used to win in silence.

    That is YAML's own rule, and it is the one remaining way to get a page
    nobody asked for out of a configuration `check` calls clean — a setting
    added at the top of a section, already set twelve lines further down.
    """

    def test_a_repeated_key_is_refused(self):
        with pytest.raises(yaml_loader.DuplicateKeyError):
            yaml_loader.load("header:\n  height: 30mm\n  show: true\n  height: 43mm\n")

    def test_the_error_carries_the_key_and_both_lines(self):
        with pytest.raises(yaml_loader.DuplicateKeyError) as caught:
            yaml_loader.load("header:\n  height: 30mm\n  show: true\n  height: 43mm\n")
        assert caught.value.key == "height"
        assert (caught.value.first_line, caught.value.second_line) == (2, 4)

    def test_a_repeat_at_the_top_level_is_refused_too(self):
        with pytest.raises(yaml_loader.DuplicateKeyError) as caught:
            yaml_loader.load("fonts:\n  serif: [X]\npage:\n  size: a4\nfonts:\n  mono: [Y]\n")
        assert caught.value.key == "fonts"
        assert (caught.value.first_line, caught.value.second_line) == (1, 5)

    def test_a_repeat_inside_a_list_entry_is_refused(self):
        # `footer.columns` and `header.fields.items` are lists of records, and
        # a record is where a hand-written key is most easily written twice.
        with pytest.raises(yaml_loader.DuplicateKeyError) as caught:
            yaml_loader.load("columns:\n  - title: A\n    rows: []\n    title: B\n")
        assert caught.value.key == "title"

    def test_two_spellings_of_the_same_key_are_one_key(self):
        # YAML 1.1 reads both as the boolean true, which is the trap that makes
        # `footer.pages` spelled the way it is. Two of them is still a repeat.
        with pytest.raises(yaml_loader.DuplicateKeyError) as caught:
            yaml_loader.load("footer:\n  on: last\n  yes: all\n")
        assert caught.value.key is True

    def test_the_error_is_one_pyyaml_callers_already_catch(self):
        # Anything reading YAML through this module reports a message rather
        # than a traceback even if it knows nothing about the new class.
        with pytest.raises(yaml.YAMLError):
            yaml_loader.load("a: 1\na: 2\n")


class TestWhatStaysLegal:
    def test_a_file_without_repeats_loads_as_before(self):
        loaded = yaml_loader.load("brand:\n  name: Acme\npage:\n  size: a4\n")
        assert loaded == {"brand": {"name": "Acme"}, "page": {"size": "a4"}}

    def test_an_empty_file_is_none_as_before(self):
        assert yaml_loader.load("") is None

    def test_the_same_key_in_two_different_mappings_is_two_keys(self):
        loaded = yaml_loader.load("header:\n  ink: '#fff'\nfooter:\n  ink: '#000'\n")
        assert loaded == {"header": {"ink": "#fff"}, "footer": {"ink": "#000"}}

    def test_a_merge_key_may_still_be_overridden(self):
        # The check runs over the keys as written, before PyYAML flattens a
        # `<<` into them. Overriding something merged in is the point of
        # merging, and is not a repeat.
        loaded = yaml_loader.load(
            "base: &base\n  size: a4\n  ink: '#000'\n"
            "page:\n  <<: *base\n  ink: '#333'\n"
        )
        assert loaded["page"] == {"size": "a4", "ink": "#333"}

    def test_a_key_that_cannot_be_hashed_is_still_pyyaml_s_to_refuse(self):
        # Not a repeat, and not this module's business — but it must not come
        # out as a TypeError from inside the duplicate check either.
        with pytest.raises(yaml.constructor.ConstructorError):
            yaml_loader.load("? [a, b]\n: value\n")
