# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] — 2026-09-19

### Fixed

- A setting whose name has the shape of a language tag no longer swallows the
  section holding it. `page.margin: { top: 30mm }` was read as a translation
  into a language spelled `top`, which replaced the whole margin with the
  string `30mm` and then failed with a `TypeError` out of Python rather than an
  error naming the setting. Language maps are now recognised against the
  schema — a section owns its own key names — so `top`, `ink`, `fit` and every
  short key added from here on are keys wherever the schema says they are.
  `brand.tagline: { en: ..., de: ... }` still replaces the section, because it
  borrows none of that section's names.
- `mela-letterhead check` now resolves the letterhead and every document it
  discovers, exactly as `build` would. It read the configuration and stopped
  there, so a colour that was not one, a weight outside 100–900 or a malformed
  footer row passed `check` with "Everything checks out." and failed on the
  very next command. A value written per language is resolved in each
  document's own language, and reported against the document that meets it.

## [0.2.0] — 2026-09-19

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
- `page.background`: a picture behind the page — a sheet designed elsewhere, a
  watermark, a texture. Read relative to the configuration like the logo, drawn
  under the border and the bands, with `fit` (`cover` or `contain`), `pages`
  (`first`, `rest` or `all`) and `veil`, a white overlay that keeps text
  readable over a busy picture. Turn the header, running header and footer off
  and the tool sets Markdown onto paper somebody else designed. Typst places no
  PDF, so such a sheet has to be exported raster; and since Typst has no image
  opacity the veil is literally a translucent white rectangle, which works on
  white paper and nowhere else.
- `units.to_alpha`, a share bounded to nought…one, for a value that is an
  opacity rather than a width.

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
- `mela-letterhead check` reports the page background when one is set, and
  fails when the file is not there.

### Fixed

- `brand.logo` written as a language map — a brand with a different mark per
  market — was staged as the printed form of the mapping and reported as a
  missing file. The logo and the page background are now both staged from the
  resolved configuration, in the document's own language, as the documentation
  has always said they were.

[Unreleased]: https://github.com/melasistema/mela-letterhead/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/melasistema/mela-letterhead/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/melasistema/mela-letterhead/releases/tag/v0.2.0
