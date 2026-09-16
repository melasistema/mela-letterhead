"""Markdown documents and their front matter.

A document carries the values that change from one piece of paper to the next —
its type, its reference number, its date — in a YAML front-matter block::

    ---
    title: Quotation for the Terlan waterworks
    lang: de
    type: Kostenvoranschlag
    reference: XLKN1BSZ86
    date: "14.09.2026"
    ---

A handful of keys are the tool's own (see :data:`RESERVED_KEYS`). Every other
key is yours, and reaches the letterhead through a header field that names it::

    header:
      fields:
        items:
          - key: reference
            label: { en: "Reference", de: "Kennzeichen" }

So the set of header fields is not fixed at four, or at any number: it is
whatever the brand's paper happens to have on it.
"""

from __future__ import annotations

import datetime as _datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .errors import DocumentError

#: Front-matter keys the tool reads itself. Everything else is a header field.
RESERVED_KEYS = frozenset(
    {
        "title",
        "running-title",
        "running_title",
        "lang",
        "language",
        "output",
        "author",
    }
)

_FRONT_MATTER_RE = re.compile(
    r"\A﻿?(?:---|\+\+\+)[ \t]*\r?\n(?P<body>.*?)\r?\n(?:---|\.\.\.|\+\+\+)[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


class Document:
    """One Markdown source file, split into front matter and body."""

    def __init__(
        self,
        path: Path,
        metadata: Dict[str, Any],
        body: str,
        date_format: str = "%Y-%m-%d",
    ) -> None:
        self.path = path
        self.metadata = metadata
        self.body = body
        self.date_format = date_format

    # -- construction -----------------------------------------------------

    @classmethod
    def load(cls, path: Path, date_format: str = "%Y-%m-%d") -> "Document":
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise DocumentError(f"{path}: no such file") from None
        except OSError as exc:
            raise DocumentError(f"{path}: {exc.strerror or exc}") from exc
        except UnicodeDecodeError as exc:
            raise DocumentError(
                f"{path}: the file is not valid UTF-8",
                hint="Re-save it as UTF-8; Markdown sources are read as UTF-8 only.",
            ) from exc

        metadata, body = split_front_matter(text, path)
        return cls(path, metadata, body, date_format)

    # -- the tool's own keys ----------------------------------------------

    @property
    def title(self) -> str:
        """The document title, from front matter or the first heading."""
        title = self.metadata.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        return self._first_heading() or self.path.stem

    @property
    def running_title(self) -> str:
        """What the running header shows. Falls back to the title."""
        value = self.metadata.get("running-title") or self.metadata.get("running_title")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return self.title

    @property
    def language(self) -> Optional[str]:
        """The document's language, if it declares one."""
        value = self.metadata.get("lang") or self.metadata.get("language")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @property
    def author(self) -> Optional[str]:
        value = self.metadata.get("author")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @property
    def output_name(self) -> str:
        """Stem of the PDF to write, without the extension."""
        value = self.metadata.get("output")
        if isinstance(value, str) and value.strip():
            return Path(value.strip()).stem
        return self.path.stem

    @property
    def slug(self) -> str:
        """A filesystem-safe name for this document's build directory."""
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", self.path.stem).strip("-")
        return slug or "document"

    # -- user keys --------------------------------------------------------

    def field(self, key: str) -> Optional[str]:
        """The front-matter value for ``key``, as a string, or ``None``.

        Dates are formatted rather than stringified: YAML turns an unquoted
        ``2026-09-14`` into a date object, and ``str()`` on that would print an
        ISO date on paper that asks for ``14.09.2026``.
        """
        if key in self.metadata:
            return self._stringify(self.metadata[key])
        # Front matter written in kebab-case should answer to a snake_case key
        # and the other way round, so neither spelling is a silent miss.
        for alternative in (key.replace("_", "-"), key.replace("-", "_")):
            if alternative in self.metadata:
                return self._stringify(self.metadata[alternative])
        return None

    def _stringify(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (_datetime.datetime, _datetime.date)):
            return value.strftime(self.date_format)
        if isinstance(value, (list, tuple)):
            return ", ".join(filter(None, (self._stringify(item) for item in value)))
        text = str(value).strip()
        return text or None

    def _first_heading(self) -> Optional[str]:
        for line in self.body.splitlines():
            match = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
            if match and match.group(1).strip():
                # Strip the commonest inline markup; a title is not a place for it.
                return re.sub(r"[*_`]", "", match.group(1)).strip()
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Document {self.path.name!r}>"


def split_front_matter(text: str, path: Optional[Path] = None) -> "tuple[Dict[str, Any], str]":
    """Split a Markdown source into its front matter and its body.

    The body keeps its original line numbering nowhere — it is re-emitted from
    the match end — but Pandoc reports positions in the preprocessed file
    anyway, so there is nothing to preserve.
    """
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        return {}, text.lstrip("﻿")

    try:
        metadata = yaml.safe_load(match.group("body"))
    except yaml.YAMLError as exc:
        where = f"{path}: " if path else ""
        raise DocumentError(
            f"{where}the front matter is not valid YAML: {exc}",
            hint="Values containing a colon must be quoted — "
            'write `title: "Offer: phase two"`, not `title: Offer: phase two`.',
        ) from exc

    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        where = f"{path}: " if path else ""
        raise DocumentError(f"{where}the front matter must be a mapping of keys to values")

    return metadata, text[match.end() :]


def discover(
    source: Path,
    include: List[str],
    exclude: List[str],
) -> List[Path]:
    """Find the Markdown sources under ``source`` matching ``include``.

    Patterns are matched against the path relative to ``source``, so a pattern
    may address a subdirectory (``offers/*.md``) as well as a bare name.
    """
    if not source.is_dir():
        raise DocumentError(f"{source}: no such directory")

    found: Dict[Path, None] = {}
    for pattern in include:
        for path in sorted(source.glob(pattern)):
            if path.is_file():
                found[path.resolve()] = None

    kept = []
    for path in found:
        relative = path.relative_to(source.resolve())
        if any(_matches(relative, pattern) for pattern in exclude):
            continue
        kept.append(path)
    return sorted(kept)


def _matches(relative: Path, pattern: str) -> bool:
    from fnmatch import fnmatch

    return fnmatch(str(relative), pattern) or fnmatch(relative.name, pattern)
