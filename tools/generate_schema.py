#!/usr/bin/env python3
"""Generate ``assets/letterhead.schema.json`` from ``DEFAULT_CONFIG``.

What this buys, in one sentence: **`_reject_unknown_keys`'s answer, in the
editor, before anything is run.** An editor with `yaml-language-server` in it —
which is what VS Code's Red Hat YAML extension, Neovim, Helix and Zed all use —
underlines `pallette:` while it is being typed, and the scaffold's first line is
what points it here.

Run by hand and by CI::

    python tools/generate_schema.py           # write the file
    python tools/generate_schema.py --check   # fail if it is out of date

**Nothing fetches this over the network, and nothing should.** The scaffold's
modeline is a relative path, the schema is copied into the project beside the
letterhead it describes, and the copy is the one belonging to the installed
version. A URL would mean a file to serve forever, an editor that needs the
network to help, and a schema drifting out of step with the `pipx install`
being checked against it — and when the URL is merely not there yet, the editor
does not fall quiet, it underlines the letterhead and says it cannot load a
schema. So the generator writes into the package and `mela-letterhead schema`
is what hands a project the copy: a subcommand for a file that changes once a
release, which is worth it only because it is the *only* way to get the file.

**The descriptions are the comments in `config.py`.** They are already written
in the register a hover tooltip wants, so they are harvested rather than
written again: `ast` gives every key of the `DEFAULT_CONFIG` literal a line
number, `tokenize` gives every comment one, and a key's description is the run
of comment lines immediately above it — plus the trailing one on its own line,
which is how the palette is commented. The dict is never re-implemented from
the syntax tree: importing the module gives the *values*, the tree gives only
the *line numbers*, and walking both together keyed by dotted path is what
pairs them.

**Every vocabulary comes from the module, not from here.** The table below maps
a dotted path to a tuple that already exists in `config` or `units`, so a
standard added to `PDF_STANDARDS` reaches the schema with no second edit.

**What the schema deliberately cannot say.** It describes the *written* shape,
and the thing the tool is cleverest about has no expression in JSON Schema:
that a mapping is a translation only where it borrows none of its section's key
names. So it is loose in one direction — `$defs/length` accepts a length, a
share and a multiple of the font size wherever any of them is written, because
which family a setting belongs to lives in its resolver — and stricter in
exactly one place: a whole *section* written once per language
(`header: { en: …, de: … }`) is refused here though the tool allows it.
`brand.tagline`, the one section documented as writable either way, is spelt
out. An editor that flags nothing has done its job; `check` is still the thing
that says yes.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mela_letterhead import config as config_module  # noqa: E402
from mela_letterhead import i18n, units  # noqa: E402

#: Inside the package, because that is what `pipx install` carries. The file is
#: generated here and committed there: `init` copies it out beside the
#: letterhead it writes, and the schema a project is checked against is the one
#: belonging to the version that wrote it.
SCHEMA_PATH = ROOT / "src" / "mela_letterhead" / "assets" / "letterhead.schema.json"
CONFIG_SOURCE = ROOT / "src" / "mela_letterhead" / "config.py"

#: The shape of a language key, taken from the module that decides it.
TAG = i18n._LANGUAGE_TAG_RE.pattern

#: Every unit a length may carry. The absolute ones are read from the table
#: that converts them; `em` and `%` are the two relative families, which have
#: no such table because nothing converts them here.
UNITS = sorted(units._POINTS_PER_UNIT) + ["em", "%"]

MEASURE_PATTERN = rf"^\s*[+-]?(?:\d+(?:\.\d+)?|\.\d+)\s*(?:{'|'.join(UNITS)})?\s*$"


# ---------------------------------------------------------------------------
# the comments in config.py
# ---------------------------------------------------------------------------


def descriptions(source_path: Path) -> dict[str, str]:
    """Every dotted path in ``DEFAULT_CONFIG`` that has a comment, and it."""
    source = source_path.read_text(encoding="utf-8")
    comments = _comments(source)
    found: dict[str, str] = {}
    _walk(_default_config_node(ast.parse(source)), "", comments, found)
    return found


def _default_config_node(tree: ast.Module) -> ast.Dict:
    target: ast.expr
    assigned: ast.expr | None
    for statement in tree.body:
        if isinstance(statement, ast.AnnAssign):
            target, assigned = statement.target, statement.value
        elif isinstance(statement, ast.Assign) and statement.targets:
            target, assigned = statement.targets[0], statement.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id == "DEFAULT_CONFIG":
            if not isinstance(assigned, ast.Dict):
                raise SystemExit("DEFAULT_CONFIG is no longer a dict literal")
            return assigned
    raise SystemExit(f"no DEFAULT_CONFIG assignment in {CONFIG_SOURCE}")


def _comments(source: str) -> dict[int, tuple[str, bool]]:
    """Each comment by line number, and whether it is on a line of its own."""
    found: dict[int, tuple[str, bool]] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        alone = not token.line[: token.start[1]].strip()
        found[token.start[0]] = (re.sub(r"^#+:?[ \t]?", "", token.string).rstrip(), alone)
    return found


def _walk(
    node: ast.Dict,
    prefix: str,
    comments: dict[int, tuple[str, bool]],
    found: dict[str, str],
) -> None:
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            continue
        path = f"{prefix}{key.value}"
        text = _description_at(key.lineno, comments)
        if text:
            found[path] = text
        if isinstance(value, ast.Dict):
            _walk(value, f"{path}.", comments, found)


def _description_at(lineno: int, comments: dict[int, tuple[str, bool]]) -> str:
    """The run of comment lines above a key, and the one beside it.

    A blank line above stops the run, so a comment belonging to the section
    rather than to the key below it is not stolen; a bare ``#`` inside the run
    is a paragraph break, which is how the longer comments are written.
    """
    lines: list[str] = []
    line = lineno - 1
    while line in comments and comments[line][1]:
        lines.append(comments[line][0])
        line -= 1
    lines.reverse()

    beside = comments.get(lineno)
    if beside is not None and not beside[1]:
        lines.append(beside[0])
    return _paragraphs(lines)


def _paragraphs(lines: list[str]) -> str:
    made: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            made.append(" ".join(current))
            current = []
    if current:
        made.append(" ".join(current))
    return "\n\n".join(made)


# ---------------------------------------------------------------------------
# the pieces every setting is built out of
# ---------------------------------------------------------------------------


def translatable(base: dict[str, Any]) -> dict[str, Any]:
    """``base``, or one ``base`` per language.

    Any text in the file may be written as ``{ en: …, de: … }``, and this is
    the one thing a naive generator gets wrong. Getting it wrong would make the
    schema worse than none at all: it would underline every translated label in
    the file.
    """
    return {
        "oneOf": [
            base,
            {
                "type": "object",
                "patternProperties": {TAG: base},
                "additionalProperties": False,
                "minProperties": 1,
            },
        ]
    }


def ref(name: str) -> dict[str, Any]:
    return {"$ref": f"#/$defs/{name}"}


def enum(names: Any) -> dict[str, Any]:
    return {"enum": list(names)}


def _case_insensitively(word: str) -> str:
    """``a4`` as a pattern that also matches ``A4``.

    `page.size` is lowercased before it is looked up, and A4 is how a person
    writes A4. The pattern is generated rather than typed, so nothing here has
    to be kept in step with the table of sizes.
    """
    return "".join(f"[{c}{c.upper()}]" if c.isalpha() else re.escape(c) for c in word)


def _page_size() -> dict[str, Any]:
    names = sorted(units._PAGE_SIZES_MM)
    spelt = [*names, *(f"{name}-landscape" for name in names)]
    landscape = "".join(f"[{c}{c.upper()}]" for c in "landscape")
    return {
        "anyOf": [
            # The enum is what an editor offers; the pattern is what keeps the
            # other two spellings of landscape, and any capitalisation, from
            # being underlined for no reason.
            enum(spelt),
            {
                "type": "string",
                "pattern": "^(?:"
                + "|".join(_case_insensitively(name) for name in names)
                + f")(?:[-_ ]{landscape})?$",
            },
            {
                "type": "object",
                "properties": {"width": ref("length"), "height": ref("length")},
                "required": ["width", "height"],
                "additionalProperties": False,
            },
        ]
    }


def _defs() -> dict[str, Any]:
    return {
        "text": translatable({"type": "string"}),
        "colour": translatable(
            {"type": "string", "pattern": units._HEX_COLOUR_RE.pattern}
        ),
        "length": translatable(
            {
                "oneOf": [
                    {"type": "number"},
                    {"type": "string", "pattern": MEASURE_PATTERN},
                ]
            }
        ),
        # Not "fonts": each top-level section becomes a definition under its
        # own name, and `fonts:` is one of them.
        "fontStack": translatable(
            {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}, "minItems": 1},
                ]
            }
        ),
        "weight": {
            "oneOf": [
                {"type": "integer", "minimum": 100, "maximum": 900},
                enum(config_module._FONT_WEIGHTS),
            ]
        },
        "headerField": {
            "type": "object",
            "description": "One field printed in the header band. 'key' takes "
            "the value from the document's front matter; 'value' sets it here.",
            "properties": {
                "key": {"type": "string"},
                "label": ref("text"),
                "value": ref("text"),
            },
        },
        "footerColumn": {
            "type": "object",
            "description": "One column of the footer band.",
            "properties": {
                "title": ref("text"),
                "rows": {"type": "array", "items": ref("footerRow")},
            },
        },
        "footerRow": {
            "description": "A line, a [label, value] pair, or the full form.",
            "oneOf": [
                ref("text"),
                {"type": "array", "items": ref("text"), "minItems": 2, "maxItems": 2},
                {
                    "type": "object",
                    "properties": {
                        "label": ref("text"),
                        "value": ref("text"),
                        "link": ref("text"),
                        "style": enum(config_module._ROW_STYLES),
                    },
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# which setting is which
# ---------------------------------------------------------------------------

#: Settings whose shape cannot be read off their default value. Everything on
#: the right comes from `config` or `units` rather than from a list kept here.
BY_PATH: dict[str, Any] = {
    "version": {"type": "integer", "minimum": 1},
    "language": {"type": "string", "pattern": TAG},
    "build_dir": {"type": "string"},
    "brand.logo": ref("text"),
    "brand.tagline": None,  # filled in below: a line of text, or the section
    "page.size": _page_size(),
    "page.border.sides": {
        "oneOf": [
            enum(config_module._BORDER_SIDES),
            {"type": "array", "items": enum(config_module._BORDER_SIDES)},
        ]
    },
    "page.background.image": ref("text"),
    "page.background.fit": enum(config_module._BACKGROUND_FITS),
    "page.background.pages": enum(config_module._BACKGROUND_PAGES),
    "page.background.veil": {
        "oneOf": [
            {"type": "number", "minimum": 0, "maximum": 1},
            {"type": "string", "pattern": r"^\s*\d+(?:\.\d+)?\s*%\s*$"},
        ]
    },
    "fonts.paths": {
        "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]
    },
    "images.width": {"oneOf": [enum(("auto", "natural")), ref("length")]},
    "header.fields.when_empty": enum(config_module._WHEN_EMPTY),
    "header.fields.items": {"type": "array", "items": ref("headerField")},
    "footer.pages": enum(config_module._FOOTER_PAGES),
    "footer.columns": {"type": "array", "items": ref("footerColumn")},
    "markdown.format": {"type": "string"},
    "markdown.extra_args": {"type": "array", "items": {"type": "string"}},
    "pdf.standard": {
        "oneOf": [
            enum(config_module.PDF_STANDARDS),
            {"type": "array", "items": enum(config_module.PDF_STANDARDS)},
        ]
    },
    "documents.source": {"type": "string"},
    "documents.output": {"type": "string"},
    "documents.include": {"type": "array", "items": {"type": "string"}},
    "documents.exclude": {"type": "array", "items": {"type": "string"}},
    "documents.date_format": {"type": "string"},
}

#: The last segment of a path decides these, wherever they appear: every band
#: has a `fill`, every block of type an `align`.
BY_NAME: dict[str, Any] = {
    "align": enum(config_module._ALIGNMENTS),
    "weight": ref("weight"),
    "font": ref("fontStack"),
    "color": ref("colour"),
    "fill": ref("colour"),
    "ink": ref("colour"),
    "muted": ref("colour"),
    "highlight": ref("colour"),
    "rule_color": ref("colour"),
}


def node(path: str, value: Any, notes: dict[str, str]) -> dict[str, Any]:
    """The schema for one setting, wherever its shape comes from."""
    schema = _shape(path, value, notes)
    description = notes.get(path)
    if description and "description" not in schema:
        # Beside a `$ref` rather than inside it, which draft 2020-12 allows and
        # every language server in use reads.
        schema = {**schema, "description": description}
    return schema


def _shape(path: str, value: Any, notes: dict[str, str]) -> dict[str, Any]:
    name = path.rpartition(".")[2]

    if path in BY_PATH and BY_PATH[path] is not None:
        return dict(BY_PATH[path])
    if path == "brand.tagline":
        # Written either way: `{ text:, size: }` is the section, a plain string
        # is the text, and a language map is a translation of one or the other.
        return {"oneOf": [ref("text"), _object(path, value, notes, described=False)]}
    if path.startswith("fonts.") and isinstance(value, (list, str, type(None))):
        return ref("fontStack")
    if name in BY_NAME:
        return dict(BY_NAME[name])

    if isinstance(value, dict):
        return _object(path, value, notes)
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return ref("length")
    if isinstance(value, str):
        return ref("length") if re.match(MEASURE_PATTERN, value) else ref("text")
    if isinstance(value, list):
        return {"type": "array"}
    return ref("text")  # every remaining default is None, and all of them are text


def _object(
    path: str, mapping: dict[str, Any], notes: dict[str, str], described: bool = True
) -> dict[str, Any]:
    """A section, with `additionalProperties: false` — the schema's half of
    `_reject_unknown_keys`, and the reason the editor and the tool give the
    same answer about `colours:`."""
    schema: dict[str, Any] = (
        _palette(mapping, notes)
        if path == "palette"
        else {
            "type": "object",
            "properties": {
                key: node(f"{path}.{key}" if path else key, value, notes)
                for key, value in mapping.items()
            },
            "additionalProperties": False,
        }
    )
    if described and notes.get(path):
        schema = {"description": notes[path], **schema}
    return schema


def _palette(mapping: dict[str, Any], notes: dict[str, str]) -> dict[str, Any]:
    """The one section that holds user data.

    Every value in it is a colour, named or not: a brand may add colours of its
    own and reach them from anywhere a colour is written, so the open end is a
    colour too. This is the schema's half of the exemption
    `_reject_unknown_keys` already makes for the same section.
    """
    colours: dict[str, Any] = {}
    for key in mapping:
        entry = ref("colour")
        if notes.get(f"palette.{key}"):
            entry["description"] = notes[f"palette.{key}"]
        colours[key] = entry
    return {
        "type": "object",
        "properties": colours,
        "additionalProperties": ref("colour"),
    }


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------


def build() -> dict[str, Any]:
    notes = descriptions(CONFIG_SOURCE)
    defs = _defs()

    properties: dict[str, Any] = {}
    for key, value in config_module.DEFAULT_CONFIG.items():
        if isinstance(value, dict):
            # Each section is a definition of its own, so that the root and a
            # profile can both point at it rather than carrying a copy.
            if key in defs:
                raise SystemExit(
                    f"the section '{key}' has the name of a helper definition; "
                    "rename the helper in `_defs`"
                )
            defs[key] = node(key, value, notes)
            properties[key] = ref(key)
        else:
            properties[key] = node(key, value, notes)

    defs["letterhead"] = {
        "type": "object",
        "description": "Everything a letterhead can say. A profile is the same "
        "object with only the settings it changes in it.",
        "properties": dict(properties),
        "additionalProperties": False,
    }

    # No `$id`. Every reference in here is a local `#/$defs/…` fragment, so
    # nothing needs a base URI to resolve against — and an `$id` spelt as a URL
    # is an invitation to fetch it, which is the one thing this schema is not
    # for. It is a file that travels with the tool and is read off the disk.
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Mela Letterhead",
        "description": (
            "letterhead.yaml — the paper every document in this project is "
            "printed on.\n\n"
            "This describes the file as it is written. Any text in it may be "
            "written once per language. It is looser than the tool about "
            "lengths, which it accepts in every family the tool has, and "
            "stricter in one place: a whole section written once per language "
            "is flagged here though the tool allows it. Run 'mela-letterhead "
            "check' for the answer that counts."
        ),
        "type": "object",
        "properties": {
            **properties,
            "profiles": {
                "type": "object",
                "description": "Named sets of changes to the letterhead, "
                "applied with --profile or from a document's front matter.",
                "additionalProperties": ref("letterhead"),
            },
        },
        "additionalProperties": False,
        "$defs": defs,
    }


def rendered() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed schema is not what this would write",
    )
    args = parser.parse_args(argv)

    text = rendered()
    if args.check:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.is_file() else ""
        if current != text:
            print(
                f"{SCHEMA_PATH.relative_to(ROOT)} is out of date.\n"
                "Run: python tools/generate_schema.py",
                file=sys.stderr,
            )
            return 1
        print(f"{SCHEMA_PATH.relative_to(ROOT)} is up to date.")
        return 0

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
