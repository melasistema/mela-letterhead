# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Pictures in the body. `![caption](plate.svg)` prints PNG, JPEG, GIF, SVG and
  WebP; the file is read relative to the document that names it, copied into
  the document's build directory and the reference repointed at it, since Typst
  compiles with its root set there and can read nothing above it.
- An `images:` section: the default width of a picture that gives none of its
  own, the alignment of a figure, an optional hairline frame, figure numbering,
  and the size and gap of a caption. A picture with a caption is set as a
  centred figure with the caption beneath it; one without stays inline.
- `units.to_ratio`, for a width written as a share of the column — `70%` or the
  fraction `0.7`. A bare `70` is refused rather than printed seventy times too
  wide.
- Three drawings in the scaffold, and a section of the example document that
  prints them: one full-width figure with a caption, and two standing side by
  side at `{width=48%}`.

### Changed

- The example document runs to four pages, and the README screenshots were
  retaken from it.

## [0.1.0] — 2026-09-16

First release.

### Added

- `mela-letterhead init`, `build` and `check`.
- A letterhead described entirely by `letterhead.yaml`: brand, page size,
  palette, font stacks, typography, header band, running header and footer
  band.
- Header fields of any number, taking their values from a document's YAML
  front matter, with a per-field choice of what an empty value prints — a rule
  to fill in by hand, a bare label, or nothing at all.
- Footer columns of any number, with three ways to write a row, an automatic
  `mailto:` link for e-mail addresses, and a highlight style for the one row
  that has to catch the eye.
- Per-language text anywhere in the configuration: any string may be written as
  a mapping from language tag to translation, resolved along a fallback chain
  so that a half-translated letterhead still prints.
- Locale packs for the strings the tool writes itself. English ships with the
  package; a project adds a language by dropping `locales/<tag>.yaml` beside
  its configuration, with no change to any code.
- A typographic wordmark for brands with no logo file, fitted to the width the
  logo would have occupied.
- Markdown preparation: table column widths recomputed from the content,
  horizontal rules dropped, table header rows emboldened — each switchable, and
  none of them applied inside fenced code blocks.
- Configuration errors that name the offending setting and suggest the nearest
  valid one.

[Unreleased]: https://github.com/melasistema/mela-letterhead/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/melasistema/mela-letterhead/releases/tag/v0.1.0
