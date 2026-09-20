# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Python 3.10 is the floor.** 3.9 went out of support in October 2025 and the
  tooling has started to follow: mypy needs 3.10 to run, so a developer on the
  old floor could only install a checker a version behind the one CI installed —
  and the newer one, finding a `python_version` it no longer understood, warned
  and then checked against its own interpreter instead. The gate went on passing
  while it had quietly stopped testing the version the package claimed to
  support. Nothing about a letterhead changes; if you are on 3.9, 0.3.2 remains
  installable and works.
- A table's column widths are computed with the two per-column lists paired
  strictly. They have always been the same length and still are, so no table
  moves — but pairing them loosely meant a length that had drifted would have
  cost the last column its width without saying anything, and that is now an
  error instead. Found by the linter the moment the floor made the check
  available.

## [0.3.2] — 2026-09-20

### Fixed

- A setting written twice is no longer taken quietly the second time. YAML's
  rule is that the last of two keys spelled the same way wins, and PyYAML
  follows it without a word — so a height added at the top of `header:`, where
  one was already set twelve lines further down, produced a page nobody had
  asked for out of a file `check` called clean. That was the last way to get a
  wrong page with a clean report. All three files edited by hand — the
  configuration, a document's front matter and a locale pack — now refuse a
  repeated key, naming it and both of the lines it was written on, and counting
  those lines from the top of the file rather than from the top of the front
  matter. A `<<` merge key is untouched: overriding something merged in is the
  point of merging, and is not a repeat.

## [0.3.1] — 2026-09-20

### Fixed

- The command runs on Windows. `check` printed a tick, Windows hands a
  redirected command the ANSI code page rather than UTF-8, and cp1252 has no
  tick in it — so the whole command ended in a `UnicodeEncodeError` on the
  first line of its own report, before it had said anything about the
  toolchain. The tick, the cross and the arrow are now chosen to fit the stream
  being written to, falling back to `+`, `x` and `->` at the same width, and
  anything else the stream cannot take — a brand name, a path, a font family —
  degrades to a question mark instead of ending the run. This is what the
  Windows job added in 0.3.0 was for, and it found it on its first outing.

## [0.3.0] — 2026-09-20

### Added

- **Mela Letterhead is on PyPI.** `pipx install mela-letterhead` is the whole
  of it — the tool has been reachable only by cloning the repository until now,
  which is a reasonable way to work on it and an unreasonable way to use it.
  Releases are published by the tag that cuts them, with no API token anywhere:
  PyPI verifies the identity GitHub mints for the workflow. The same job checks
  that the scaffold and the locale packs travelled inside both artefacts, since
  a wheel that installs without its plates gives an `init` that writes a broken
  letterhead.
- macOS and Windows are tested on every change, alongside the Linux job that
  was there before. Nothing in this release was found by it, which is the point
  of having it before something is.
- `CONTRIBUTING.md` and `SECURITY.md`, and templates for the two kinds of
  issue. The contributing notes carry the policy for the `version:` key in
  `letterhead.yaml`, which has been 1 since the beginning with no account of
  what would make it 2: a change that would *misread* an existing file, shipped
  with a migration, never a release that can only say the file is too old.
- `markdown.extra_args` is documented, and with it the one thing in
  `letterhead.yaml` that is not a description of a page: Pandoc's
  `--lua-filter`, `--filter` and `-F` name programs and Pandoc runs them, so a
  letterhead you did not write is a script you did not write.

### Changed

- The project lints with ruff and type-checks with mypy under `--strict`, both
  on every change. Six things came out of the first strict run and are fixed
  here; none of them could reach a page, which is why they had lasted.
  `ruff format` is deliberately not run — the prose in this codebase is wrapped
  by hand, and filling it to the column would take the shape out of it.
- Coverage is measured and floored at 88%, a little under the 91% the suite
  reaches with Pandoc and Typst installed. Most of what was added to get there
  is `mela-letterhead init` and the branches of `check` that report a file it
  cannot find, neither of which any test had exercised.
- The README leads with installing the tool rather than cloning it. The clone
  is still documented, as what it is: how to work on it.

## [0.2.2] — 2026-09-20

### Added

- Pandoc and Typst are now checked against the oldest release this can be run
  on, not only against the one it was developed with. A Typst below 0.12 used
  to fail inside `letterhead.typ`, complaining about a name it had never heard
  of; it is now refused by name, with the version you have and the version you
  need. `check` reports it as a problem rather than a tick.

### Changed

- `NO_COLOR` and `FORCE_COLOR` are honoured. The decision used to be taken once,
  when the command was imported, and consulted nothing but whether standard
  output was a terminal — so a build in a CI log came out full of escape
  sequences or a terminal came out plain, with no way to say otherwise. Both
  variables are read by presence, as the convention has it, so `NO_COLOR=0` is
  still somebody asking for no colour.

### Fixed

- A length that cannot be negative no longer accepts one. `header.height: -5mm`
  was taken at its word and laid the page out in some way nobody intended; it is
  now refused where the setting can still be named. The three that mean
  something negative keep it: `running.tracking`, `footer.offset` — a band that
  bleeds past the trim — and `brand.tagline.gap`, which pulls the line back up
  into a mark with whitespace under it.
- Pandoc and Typst are given two minutes to finish rather than forever. Neither
  has any business taking that long — the four-page example builds in a fifth of
  a second — so a build that reached it was wedged, and hung with nothing on
  screen and nothing to read.

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

[Unreleased]: https://github.com/melasistema/mela-letterhead/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/melasistema/mela-letterhead/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/melasistema/mela-letterhead/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/melasistema/mela-letterhead/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/melasistema/mela-letterhead/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/melasistema/mela-letterhead/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/melasistema/mela-letterhead/releases/tag/v0.2.0
