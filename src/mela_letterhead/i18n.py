"""Language resolution.

The letterhead carries two kinds of text, and they are localised differently.

**Text the user writes** — field labels, footer rows, the brand name — lives in
``letterhead.yaml``. Any string there may be replaced by a mapping from language
tag to string::

    label: { en: "Reference", it: "Codice", de: "Kennzeichen" }

A mapping is treated as a language map when *every* key looks like a language
tag (``en``, ``pt-BR``, ``de_AT``) **and the schema is not expecting a section
there**. The second half matters as much as the first: ``top``, ``ink`` and
``fit`` all have the shape of a language tag, and a schema that owns those
names is the only thing that can say so. See :func:`is_translation`.

Subject to that, the rule is applied to the whole configuration tree, so
anything the user can write can be translated — including the logo, for a brand
with a different mark per market.

**Text the tool writes** — currently just the running-header format — comes from
a locale pack: a YAML file of structural strings. English ships with the
package; a project adds a language by dropping ``locales/<tag>.yaml`` next to
its configuration, with no change to any code.

Resolution walks a fallback chain, so a half-translated project still prints:
the document's language, then its bare language subtag, then the project
default, then English.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import yaml_loader
from .errors import ConfigError

#: ``en``, ``pt-BR``, ``de_AT``, ``zh-Hans`` — the shapes a language key may take.
_LANGUAGE_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")

#: The keys of the records a user writes *inside* the schema's lists — a header
#: field, a footer column, a footer row. Those lists hold user data, so the
#: schema describes nothing within them, and a one-key record such as
#: ``{ key: reference }`` would otherwise be read as a translation.
#:
#: This set used to carry every schema key that looked like a language tag too,
#: and had to grow with the schema; it missed ``top``, and
#: ``page.margin: { top: 30mm }`` was read as Tok Pisin. Those names are the
#: schema's business now — :func:`is_translation` asks it directly — and this
#: set is bounded by the three record shapes below rather than by the schema.
_RESERVED_KEYS = frozenset(
    {"key", "label", "value", "link", "style", "title", "rows", "items"}
)

DEFAULT_LANGUAGE = "en"


class _Unknown:
    """The schema has nothing to say about this position."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<unknown>"


#: Passed as the schema wherever there is none: inside the lists that hold a
#: user's own records, and under a key the schema leaves open. There a mapping
#: is read by its shape alone, as everything was before.
UNKNOWN = _Unknown()

_BUILTIN_LOCALES = Path(__file__).parent / "locales"


def is_language_tag(key: object) -> bool:
    """Whether ``key`` has the shape of a BCP 47 language tag."""
    return isinstance(key, str) and bool(_LANGUAGE_TAG_RE.match(key))


def is_language_map(value: object) -> bool:
    """Whether ``value`` has the *shape* of a mapping from tag to translation.

    This is the question of last resort, asked where the schema has nothing to
    say. Where it does — anywhere in ``letterhead.yaml`` — :func:`is_translation`
    is the one to ask, because a mapping's shape cannot distinguish a
    translation from a section whose keys are short words.
    """
    if not isinstance(value, dict) or not value:
        return False
    if not all(is_language_tag(key) for key in value):
        return False
    # ``{ key: reference }`` is a header field, not Kpelle.
    return not all(str(key).lower() in _RESERVED_KEYS for key in value)


def is_translation(value: object, schema: object = UNKNOWN) -> bool:
    """Whether ``value`` is a language map *in the position it was written*.

    A section owns its own key names. ``page.margin`` has an ``x``, a ``top``
    and a ``bottom``, so ``{ top: 30mm }`` written there is a margin with one
    side set — never a translation into a language that happens to be spelled
    the same. A mapping is a translation only where it borrows none of the
    section's names, which is what lets ``brand.tagline`` be written either way:
    ``{ text:, size: }`` is the section, ``{ en:, de: }`` is a translation of it.

    ``schema`` is the matching node of the written-shape schema — in practice a
    subtree of :data:`~mela_letterhead.config.DEFAULT_CONFIG`. Where it expects
    a scalar, or is :data:`UNKNOWN`, the shape decides alone.
    """
    if not is_language_map(value):
        return False
    if isinstance(schema, dict) and schema and isinstance(value, dict):
        return not any(key in schema for key in value)
    return True


def normalise_tag(tag: str) -> str:
    """Return ``tag`` in the canonical ``ll-RR`` form used for comparison."""
    parts = re.split(r"[-_]", tag.strip())
    if not parts or not parts[0]:
        raise ConfigError(f"{tag!r} is not a language tag")
    canonical = [parts[0].lower()]
    for part in parts[1:]:
        canonical.append(part.upper() if len(part) == 2 else part.capitalize())
    return "-".join(canonical)


def split_tag(tag: str) -> "tuple[str, Optional[str]]":
    """Split a language tag into the ``lang`` and ``region`` Typst expects."""
    parts = re.split(r"[-_]", tag.strip())
    language = parts[0].lower()
    region = None
    for part in parts[1:]:
        if len(part) == 2 and part.isalpha():
            region = part.upper()
            break
    return language, region


def fallback_chain(language: str, default: str = DEFAULT_LANGUAGE) -> List[str]:
    """Languages to try, in order, when looking a string up.

    ``pt-BR`` with a project default of ``it`` yields
    ``['pt-BR', 'pt', 'it', 'en']`` — each entry tried before the next.
    """
    chain: List[str] = []

    def add(tag: Optional[str]) -> None:
        if not tag:
            return
        canonical = normalise_tag(tag)
        if canonical not in chain:
            chain.append(canonical)

    add(language)
    base, _ = split_tag(language)
    add(base)
    add(default)
    if default:
        add(split_tag(default)[0])
    add(DEFAULT_LANGUAGE)
    return chain


def pick(language_map: Dict[str, Any], chain: List[str]) -> Any:
    """Choose a translation from ``language_map`` along the fallback ``chain``.

    Falls back to the first entry in the map rather than to nothing: a label in
    the wrong language still prints, an empty one leaves a hole in the page.
    """
    available = {normalise_tag(key): value for key, value in language_map.items()}
    for tag in chain:
        if tag in available:
            return available[tag]
    for tag in chain:
        base, _ = split_tag(tag)
        for candidate, value in available.items():
            if split_tag(candidate)[0] == base:
                return value
    return next(iter(language_map.values()))


def localise(value: Any, chain: List[str], schema: Any = UNKNOWN) -> Any:
    """Recursively replace every language map in ``value`` with one translation.

    ``schema`` is the matching node of the written-shape schema; pass
    :data:`~mela_letterhead.config.DEFAULT_CONFIG` to walk a whole
    configuration, and nothing at all to localise a value already lifted out of
    one. It travels down beside the value so that each mapping is judged where
    it was written rather than by its shape — see :func:`is_translation`.
    """
    if isinstance(value, dict):
        if is_translation(value, schema):
            # The chosen translation is localised in turn against the same
            # schema: a section written per language is still that section.
            return localise(pick(value, chain), chain, schema)
        return {
            key: localise(item, chain, _member(schema, key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        # A list holds the user's own records — header fields, footer columns,
        # the rows inside them — and the schema describes none of their
        # contents. Inside one, shape is all there is to go on.
        return [localise(item, chain, UNKNOWN) for item in value]
    return value


def _member(schema: Any, key: Any) -> Any:
    """The schema for ``key`` within ``schema``, or :data:`UNKNOWN`.

    A key the schema does not name — an extra colour in ``palette`` — is open
    ground, and what is written under it is read by its shape.
    """
    if isinstance(schema, dict) and key in schema:
        return schema[key]
    return UNKNOWN


def load_locale(chain: List[str], project_locales: Optional[Path] = None) -> Dict[str, Any]:
    """Merge the locale packs for ``chain``, most specific last.

    Project packs override the built-in ones for the same language, so a project
    can correct a shipped string without forking the package.
    """
    merged: Dict[str, Any] = {}
    for tag in reversed(chain):
        for directory in (_BUILTIN_LOCALES, project_locales):
            if directory is None:
                continue
            merged.update(_read_locale_file(directory, tag))
    return merged


def available_locales(project_locales: Optional[Path] = None) -> List[str]:
    """Every language tag with a locale pack, built-in or project-local."""
    tags = set()
    for directory in (_BUILTIN_LOCALES, project_locales):
        if directory is None or not directory.is_dir():
            continue
        for path in directory.glob("*.yaml"):
            tags.add(normalise_tag(path.stem))
    return sorted(tags)


def _read_locale_file(directory: Path, tag: str) -> Dict[str, Any]:
    if not directory.is_dir():
        return {}
    # Match case-insensitively: ``pt-BR.yaml`` and ``pt-br.yaml`` are one file.
    wanted = tag.lower()
    for path in directory.glob("*.yaml"):
        if path.stem.replace("_", "-").lower() != wanted:
            continue
        try:
            data = yaml_loader.load(path.read_text(encoding="utf-8")) or {}
        except yaml_loader.DuplicateKeyError as exc:
            raise ConfigError(
                f"{path}: '{exc.key}' is set twice, on line {exc.first_line} "
                f"and on line {exc.second_line}",
                hint=yaml_loader.DUPLICATE_KEY_HINT,
            ) from exc
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: a locale file must be a mapping of strings")
        return data
    return {}
