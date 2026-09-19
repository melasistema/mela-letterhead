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
- A `brand.wordmark` section. The name a brand with no logo file prints instead
  now has a face, a size, a weight, a colour, tracking and an alignment of its
  own, so a letterhead with no image in it is a design rather than a fallback.
  Its measurements are shares of the width the mark occupies — written as
  `0.17`, `17%` or `34pt` — which is what keeps the smaller mark in the running
  header the same design.
- A `brand.tagline`: a line under the mark on page one, under a logo as much as
  under a wordmark, written as a plain string or with styling of its own.
- Colours on each band: `header.fill`, `ink`, `muted` and `rule_color`, and the
  same for the footer plus `highlight`. Each falls back to the palette, so a
  band can be given real colour without dragging the block quotations and the
  code along with it — they are drawn on `palette.band` too.
- `page.border`: a rule around the paper, on every page, with a width, a
  colour, an inset and a choice of sides (`all`, `left`, `x`, a list). Drawn
  under the bands, so a full-bleed band interrupts it. Off by default.
- `units.to_share`, for a measurement written either as a share or as a length
  to be divided by a known whole.

### Changed

- A wordmark left without a colour of its own now follows the ink of whatever
  it is printed on — the header band on page one, the paper in the running
  header — instead of always taking `palette.ink`.
- `_reject_unknown_keys` no longer descends into a language map, so a section
  with a schema of its own may still be written as `{ en: ..., de: ... }`.
- The example document runs to four pages and carries a tagline, and the README
  screenshots were retaken from it.
- `mela-letterhead init` now says that a logo and a name are both finished
  letterheads, rather than telling you to supply a logo.

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
