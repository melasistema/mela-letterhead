"""Exceptions raised by mela-letterhead.

Every error the user is expected to hit — a malformed configuration, a missing
external tool, a document that cannot be parsed — derives from
:class:`LetterheadError`, so the command line can report it as a message
instead of a traceback.
"""

from __future__ import annotations


class LetterheadError(Exception):
    """Base class for every expected failure."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(LetterheadError):
    """The letterhead configuration is missing, malformed or inconsistent."""


class DocumentError(LetterheadError):
    """A Markdown document could not be read or its front matter parsed."""


class ToolchainError(LetterheadError):
    """Pandoc or Typst is missing, too old, or exited with an error."""


class BuildError(LetterheadError):
    """The build pipeline failed for a reason other than the toolchain."""
