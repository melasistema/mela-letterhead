"""The generated `assets/letterhead.schema.json`.

Two things are under test and they are different things. That the committed
file is what the generator writes — the whole staleness defence, and the reason
a new setting cannot land without the schema moving. And that the schema says
what the tool says: it has to accept the letterhead `init` writes, and refuse
the mistakes `check` refuses, or the editor and the command disagree about the
same file, which is worse than having no schema at all.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from mela_letterhead import config as config_module

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "mela_letterhead" / "assets"
SCHEMA_PATH = ASSETS / "letterhead.schema.json"
SCAFFOLD = ASSETS / "scaffold" / "letterhead.yaml"

# The generator is a tool rather than part of the package, so it is imported
# from where it lives rather than installed.
sys.path.insert(0, str(ROOT / "tools"))
import generate_schema  # noqa: E402

needs_validator = pytest.mark.skipif(
    importlib.util.find_spec("jsonschema") is None,
    reason="jsonschema is needed to validate anything against the schema",
)


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema):
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def accepts(validator, text):
    """Whether the schema accepts a fragment of a letterhead."""
    return not list(validator.iter_errors(yaml.safe_load(text)))


class TestTheCommittedFile:
    def test_it_is_what_the_generator_writes(self):
        # The five lines that keep the schema from going quietly stale: a
        # setting added to DEFAULT_CONFIG and not regenerated fails here.
        assert SCHEMA_PATH.read_text(encoding="utf-8") == generate_schema.rendered()

    def test_it_ships_inside_the_package(self):
        # Where `pipx install` can carry it. Outside the package it would need
        # a server, and a server is the thing this design does without.
        assert SCHEMA_PATH.parent.name == "assets"
        assert SCHEMA_PATH.parent.parent.name == "mela_letterhead"

    def test_nothing_in_it_asks_to_be_fetched(self, schema):
        # No `$id`, because an `$id` spelt as a URL invites a fetch, and every
        # reference here is a local fragment that needs no base to resolve
        # against. The only absolute URL allowed is the dialect's own.
        assert "$id" not in schema
        urls = set()

        def walk(node, key=None):
            if isinstance(node, dict):
                for name, value in node.items():
                    walk(value, name)
            elif isinstance(node, list):
                for value in node:
                    walk(value, key)
            elif isinstance(node, str) and node.startswith(("http://", "https://")):
                urls.add((key, node))

        walk(schema)
        assert urls == {("$schema", "https://json-schema.org/draft/2020-12/schema")}

    def test_every_reference_points_at_something(self, schema):
        defined = set(schema["$defs"])
        seen = set()

        def walk(node):
            if isinstance(node, dict):
                target = node.get("$ref")
                if isinstance(target, str):
                    seen.add(target.removeprefix("#/$defs/"))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(schema)
        assert seen <= defined

    def test_the_vocabularies_come_from_the_module(self, schema):
        # Not a copy kept in the generator: a standard added to PDF_STANDARDS
        # has to reach the schema with no second edit.
        standard = schema["$defs"]["pdf"]["properties"]["standard"]
        assert standard["oneOf"][0]["enum"] == list(config_module.PDF_STANDARDS)

    def test_the_comments_in_config_py_are_the_descriptions(self, schema):
        # The reason the generator reads `config.py` twice rather than being
        # given a table of prose to keep in step with it.
        described = schema["$defs"]["footer"]["properties"]["pages"]["description"]
        assert "final page only" in described


@needs_validator
class TestItAcceptsWhatTheToolAccepts:
    def test_the_scaffold_as_it_ships(self, validator):
        assert accepts(validator, SCAFFOLD.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "written",
        [
            "header:\n  fields:\n    items:\n      - key: ref\n"
            "        label: { en: Reference, de: Kennzeichen }\n",
            "brand:\n  tagline: { en: Surveys, it: Perizie }\n",
            "brand:\n  tagline:\n    text: Surveys\n    size: 0.06\n",
            "brand:\n  logo: { en: mark.svg, it: marchio.svg }\n",
        ],
    )
    def test_text_written_once_per_language(self, validator, written):
        # The one thing a naive generator gets wrong, and getting it wrong
        # would underline every translated label in the file.
        assert accepts(validator, written)

    @pytest.mark.parametrize(
        "written",
        [
            "page:\n  size: A4\n",  # how a person writes A4
            "page:\n  size: a4-landscape\n",
            "page:\n  size: { width: 200mm, height: 200mm }\n",
            "page:\n  margin:\n    top: 30mm\n",  # one side of a margin
            "typography:\n  leading: 0.82\n",  # a multiple of the font size
            "running:\n  tracking: -0.2pt\n",  # negative on purpose
            "images:\n  width: '70%'\n",
            "images:\n  width: auto\n",
            "page:\n  border:\n    sides: [left, top]\n",
            "fonts:\n  serif: Georgia\n",  # one name rather than a stack
            "brand:\n  wordmark:\n    weight: semibold\n",
            "palette:\n  seafoam: '#9fd8c8'\n",  # a colour of the brand's own
            "pdf:\n  standard: [a-3b, ua-1]\n",
            "footer:\n  columns:\n    - title: Acme\n      rows:\n"
            "        - a line with no label\n"
            "        - ['Tel.', '+00 000']\n"
            "        - { label: Mail, value: a@b.c, style: highlight }\n",
            "profiles:\n  draft:\n    palette:\n      accent: '#a4262c'\n",
            # A profile may be named anything, including a language tag.
            "profiles:\n  de:\n    page:\n      size: a5\n",
        ],
    )
    def test_the_shapes_the_file_is_written_in(self, validator, written):
        assert accepts(validator, written)


@needs_validator
class TestItRefusesWhatTheToolRefuses:
    @pytest.mark.parametrize(
        "written",
        [
            "pallette:\n  accent: '#fff'\n",  # the mistyped section
            "header:\n  heigth: 43mm\n",
            "header:\n  fields:\n    when_emty: hide\n",
            "profiles:\n  draft:\n    palete:\n      accent: '#000'\n",
            "palette:\n  accent: dark purple\n",
            "page:\n  size: a9\n",
            "brand:\n  wordmark:\n    weight: 1200\n",
            "header:\n  fields:\n    when_empty: line\n",
            "pdf:\n  standard: [a2b]\n",
            "page:\n  background:\n    veil: 2\n",
            # `on:` is the boolean true in YAML 1.1, which is the whole reason
            # the setting is spelled `pages:`.
            "footer:\n  pages: on\n",
        ],
    )
    def test_the_mistakes_check_names(self, validator, written):
        assert not accepts(validator, written)

    def test_a_whole_section_per_language_is_the_known_divergence(self, validator):
        # Written down rather than fixed. JSON Schema cannot express "a mapping
        # is a translation only where it borrows none of its section's names",
        # so this one form is flagged in the editor although the tool allows
        # it. `brand.tagline`, the case anybody actually writes, is spelt out
        # in the schema and is asserted above.
        assert not accepts(validator, "header:\n  en:\n    height: 40mm\n")
