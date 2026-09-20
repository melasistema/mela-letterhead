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

Two of the tool's own keys are about the letterhead rather than about the
document. ``profile:`` names one of the project's profiles, and ``letterhead:``
is a block of settings this one document changes::

    ---
    title: Offer — phase two
    profile: draft
    letterhead:
      palette:
        accent: "#a4262c"
    ---

Both are merged in :func:`~mela_letterhead.config.resolve`, which is where the
letterhead's written shape is settled for one document.
"""

from __future__ import annotations

import datetime as _datetime
import re
from pathlib import Path
from typing import Any

import yaml

from . import yaml_loader
from .errors import DocumentError

#: Front-matter keys the tool reads itself. Everything else is a header field.
#:
#: ``letterhead`` and ``profile`` are here for a reason worth knowing: without
#: them a header field could name ``letterhead`` and stringify a whole mapping
#: of settings onto the page.
RESERVED_KEYS = frozenset(
    {
        "title",
        "running-title",
        "running_title",
        "lang",
        "language",
        "output",
        "author",
        "letterhead",
        "profile",
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
        metadata: dict[str, Any],
        body: str,
        date_format: str = "%Y-%m-%d",
    ) -> None:
        self.path = path
        self.metadata = metadata
        self.body = body
        self.date_format = date_format

    # -- construction -----------------------------------------------------

    @classmethod
    def load(cls, path: Path, date_format: str = "%Y-%m-%d") -> Document:
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
    def language(self) -> str | None:
        """The document's language, if it declares one."""
        value = self.metadata.get("lang") or self.metadata.get("language")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @property
    def author(self) -> str | None:
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
    def overrides(self) -> dict[str, Any]:
        """The ``letterhead:`` block — what this document alone changes.

        Written exactly as ``letterhead.yaml`` is written, because it is merged
        onto it in that shape and localised afterwards: a value here may be a
        language map like any other.

        Nothing is validated here. The names and the values are the schema's
        business, and are refused where the profile's are, by the same
        function, so that one mistyped setting reads the same wherever it was
        written.
        """
        value = self.metadata.get("letterhead")
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise DocumentError(
                f"{self.path}: 'letterhead' must be a mapping of settings, "
                f"got {value!r}",
                hint="It is written like the file it overrides:\n"
                "  letterhead:\n"
                "    palette:\n"
                "      accent: '#a4262c'",
            )
        return value

    @property
    def profile(self) -> str | None:
        """The profile this document asks for, if it asks for one."""
        value = self.metadata.get("profile")
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise DocumentError(
                f"{self.path}: 'profile' must be the name of a profile, got {value!r}",
                hint="Profiles are defined under 'profiles:' in letterhead.yaml.",
            )
        return value.strip()

    @property
    def slug(self) -> str:
        """A filesystem-safe name for this document's build directory."""
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", self.path.stem).strip("-")
        return slug or "document"

    # -- user keys --------------------------------------------------------

    def field(self, key: str) -> str | None:
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

    def _stringify(self, value: Any) -> str | None:
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

    def _first_heading(self) -> str | None:
        for line in self.body.splitlines():
            match = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
            if match and match.group(1).strip():
                # Strip the commonest inline markup; a title is not a place for it.
                return re.sub(r"[*_`]", "", match.group(1)).strip()
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Document {self.path.name!r}>"


def split_front_matter(text: str, path: Path | None = None) -> tuple[dict[str, Any], str]:
    """Split a Markdown source into its front matter and its body.

    The body keeps its original line numbering nowhere — it is re-emitted from
    the match end — but Pandoc reports positions in the preprocessed file
    anyway, so there is nothing to preserve.
    """
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        return {}, text.lstrip("﻿")

    try:
        metadata = yaml_loader.load(match.group("body"))
    except yaml_loader.DuplicateKeyError as exc:
        where = f"{path}: " if path else ""
        # The front matter is parsed on its own, so its lines are numbered from
        # one again; the person reading the error counts from the top of the
        # file, which is a few lines further up.
        offset = text[: match.start("body")].count("\n")
        raise DocumentError(
            f"{where}the front matter sets '{exc.key}' twice, on line "
            f"{exc.first_line + offset} and on line {exc.second_line + offset}",
            hint=yaml_loader.DUPLICATE_KEY_HINT,
        ) from exc
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
    include: list[str],
    exclude: list[str],
    skip: Path | None = None,
) -> list[Path]:
    """Find the Markdown sources under ``source`` matching ``include``.

    Patterns are matched against the path relative to ``source``, so a pattern
    may address a subdirectory (``offers/*.md``) as well as a bare name.

    ``skip`` is a directory holding no documents whatever the patterns say — in
    practice the build directory. A build stages each document's rewritten
    Markdown there as ``body.prep.md`` and removes it again only when the build
    *succeeds*, so a failure, or ``--keep-build``, leaves one behind. A
    recursive pattern such as ``**/*.md`` would then find it and build the
    rewritten copy as though it were a source: the pictures in it are already
    repointed at the staging directory, so the run fails by reporting the
    previous error against a file the user has since fixed, out of a directory
    they never wrote in. Skipping is done here rather than by a pattern in
    ``documents.exclude`` because ``build_dir`` is a setting, and a pattern
    could not follow a user who moved it.
    """
    if not source.is_dir():
        raise DocumentError(f"{source}: no such directory")

    root = source.resolve()
    pruned = skip.resolve() if skip is not None else None
    # A `skip` that contains the sources themselves is not a build directory
    # but a misconfiguration, and honouring it would discover nothing at all.
    # The patterns win, and the build reports whatever they find.
    if pruned is not None and root.is_relative_to(pruned):
        pruned = None

    found: dict[Path, None] = {}
    for pattern in include:
        for path in sorted(source.glob(pattern)):
            if path.is_file():
                found[path.resolve()] = None

    kept = []
    for path in found:
        if pruned is not None and path.is_relative_to(pruned):
            continue
        relative = path.relative_to(root)
        if any(_matches(relative, pattern) for pattern in exclude):
            continue
        kept.append(path)
    return sorted(kept)


def _matches(relative: Path, pattern: str) -> bool:
    from fnmatch import fnmatch

    return fnmatch(str(relative), pattern) or fnmatch(relative.name, pattern)
