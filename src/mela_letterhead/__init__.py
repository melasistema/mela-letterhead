"""mela-letterhead — Markdown to branded PDF, in any language.

A thin, configuration-driven layer over Pandoc and Typst: you write Markdown,
describe your letterhead once in ``letterhead.yaml``, and get PDFs on your own
paper — header band, running header, footer with your legal details — in
whatever language each document declares.
"""

# The comment is not decoration: release-please rewrites the line it marks, and
# this is the only place the version is kept besides pyproject.toml.
__version__ = "0.1.0"  # x-release-please-version
__author__ = "Luca Visciola (Melasistema)"
__license__ = "MIT"

__all__ = ["__version__", "__author__", "__license__"]
