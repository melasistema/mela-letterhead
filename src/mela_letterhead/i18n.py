"""Language resolution.

The letterhead carries two kinds of text, and they are localised differently.

**Text the user writes** — field labels, footer rows, the brand name — lives in
``letterhead.yaml``. Any string there may be replaced by a mapping from language
tag to string::

    label: { en: "Reference", it: "Codice", de: "Kennzeichen" }

A mapping is treated as a language map when *every* key looks like a language
tag (``en``, ``pt-BR``, ``de_AT``). That rule is applied to the whole
configuration tree, so anything the user can write can be translated — including
the logo, for a brand with a different mark per market.

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

from .errors import ConfigError

#: ``en``, ``pt-BR``, ``de_AT``, ``zh-Hans`` — the shapes a language key may take.
_LANGUAGE_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")

#: Words that look like language tags but are configuration keys. A mapping
#: whose keys are all drawn from this set is never a language map.
_RESERVED_KEYS = frozenset(
    {
        "on",
        "off",
        "x",
        "y",
        "show",
        "size",
        "file",
        "align",
        "width",
        "height",
        "label",
        "value",
        "link",
        "style",
        "key",
        "rows",
        "title",
        "items",
        "gap",
        "ink",
        "leading",
        "format",
        "rule",
    }
)

DEFAULT_LANGUAGE = "en"

_BUILTIN_LOCALES = Path(__file__).parent / "locales"


def is_language_tag(key: object) -> bool:
    """Whether ``key`` has the shape of a BCP 47 language tag."""
    return isinstance(key, str) and bool(_LANGUAGE_TAG_RE.match(key))


def is_language_map(value: object) -> bool:
    """Whether ``value`` is a mapping from language tag to translation."""
    if not isinstance(value, dict) or not value:
        return False
    if not all(is_language_tag(key) for key in value):
        return False
    # ``{ on: ... }`` is a footer option, not Occitan.
    return not all(str(key).lower() in _RESERVED_KEYS for key in value)


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


def localise(value: Any, chain: List[str]) -> Any:
    """Recursively replace every language map in ``value`` with one translation."""
    if is_language_map(value):
        return localise(pick(value, chain), chain)
    if isinstance(value, dict):
        return {key: localise(item, chain) for key, item in value.items()}
    if isinstance(value, list):
        return [localise(item, chain) for item in value]
    return value


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
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: a locale file must be a mapping of strings")
        return data
    return {}
