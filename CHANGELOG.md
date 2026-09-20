# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- An unknown `page.size` now says *where* a custom size is written. The hint
  ended "or give an explicit 'width' and 'height' instead", which is true and
  leaves out the only part a reader could not work out for themselves: the pair
  replaces the name, under the same key. The natural guess — a `width:` beside
  `size:` — is refused somewhere else entirely, as an unknown setting, so the
  hint sent people from one error to a second one. It now prints the shape,
  nested under whatever setting failed. A size that is neither a name nor a
  mapping, `size: 210`, is the same misunderstanding one branch earlier and was
  the one error here that offered nothing; it gets the same hint, and now
  quotes what was written.

### Documentation

- A section on which documents get built. `documents.include`, `exclude`,
  `source` and `output` had no prose anywhere outside the comments in
  `letterhead.yaml` — including the two traps that cost a person an afternoon:
  `exclude` *replaces* the default list rather than adding to it, so excluding
  a drafts directory quietly starts building `README.pdf`; and the output is
  flat, so with a recursive `**/*.md` pattern `offers/one.md` and
  `invoices/one.md` both write `one.pdf` and the second silently overwrites the
  first. Both now have an entry under "When something looks wrong" as well.
- A note that a project wants one `--watch` and not two. A document's build
  directory is named after the document rather than the process, so two watches
  stage the same document through the same directory; the resulting failure
  reads as a build reporting something from the run happening beside it.

## [0.5.1] — 2026-09-20

### Fixed

- The build directory is no longer searched for documents. A build stages each
  document's rewritten Markdown as `body.prep.md` and clears it again only when
  the build *succeeds*, so a failure — or `--keep-build` — leaves one on the
  disk; a recursive `documents.include`, `**/*.md`, then found it and built the
  rewritten copy as though somebody had written it. The pictures in that copy
  are already repointed at the staging directory, so the symptom was the worst
  kind: fix the mistake in your document, build again, and the *same* error
  comes back about a file you have just stopped referring to, out of a
  directory you have never written in — while `check` reports the project
  clean. It compounded, too, one directory per run, and `.letterhead-build`
  sorting first meant nothing else got built at all. `build`, `check` and
  `--watch` now ask one function what the documents are, so the three cannot
  drift apart; and the skipping is done there rather than by a pattern in
  `documents.exclude`, because `build_dir` is a setting and a pattern could not
  follow somebody who moved it.
- A directory that cannot be written now names the setting that chose it.
  Staging was the one part of the pipeline whose failures did not arrive as
  failures: a `build_dir` on a read-only mount, or one belonging to somebody
  else, came out as a `PermissionError` from inside `shutil`, several frames up
  a traceback, naming a path the user had never typed. `build_dir` and
  `documents.output` are reported by name with what to do about them, and a
  logo, a background or a picture that cannot be read is reported by *its* name
  — a copy has two ends, and the name of the file is the one attribution that
  is right whichever end failed.

## [0.5.0] — 2026-09-20

### Added

- **`build --watch`: the page redraws itself while you write.** A build is
  about two tenths of a second, so the sensible way to design a letterhead is
  to leave one running. It builds once and then builds again on every save of
  anything it read — the document, `letterhead.yaml`, a locale pack, the logo,
  the page background, and every picture the document prints. A document
  written while it is running is picked up without being named. A failed build
  does not end the session, which is the whole value of it: the error is
  printed, the file that caused it stays watched, and saving it again is what
  makes the error go away. `letterhead.yaml` is the same — half-typed YAML
  costs an error, not the session, and the previous configuration is kept until
  the file reads again. Ctrl-C exits 0, because a watch stopped on purpose is
  not a failure.
- **`profiles:`, and a per-document `letterhead:` block.** One letterhead,
  printed more than one way. A profile is a named set of changes to
  `letterhead.yaml`, written in the same shape as the part it replaces —
  `mela-letterhead build --profile draft` turns the accent red, sets a
  watermark behind every page and says DRAFT under the mark; `--profile final`
  asks for PDF/A instead. A document that is always a draft says `profile:
  draft` in its own front matter, and the flag beats the front matter, because
  the flag is something you typed one second ago about this run. Below both, a
  `letterhead:` block in front matter changes the paper for one document alone
  — the report that wants no footer band. The order is the file, then the
  profile, then the block, and all three are merged before the language is
  chosen, so an override may be written per language like anything else.
- `check --profile` reports what will happen before it happens: the profiles a
  letterhead defines, which one is active and where it came from, and a mark
  against every document carrying settings of its own. An override silently not
  applied is the failure this feature would otherwise have.
- **A JSON schema for `letterhead.yaml`, and the scaffold points at it.**
  `mela-letterhead check`'s answer about a mistyped setting, in the editor,
  before anything is run. `init` writes `letterhead.schema.json` beside the
  letterhead and the letterhead's first line is a `# yaml-language-server:`
  comment naming it, which is the whole of the setup for VS Code with the Red
  Hat YAML extension, Neovim, Helix and Zed: the setting names complete, the
  comments in the file become the tooltips, and `pallette:` is underlined
  before it is saved. Without such an editor the line is an inert comment.
- **Nothing is fetched.** The schema travels inside the package, the modeline
  is a relative path, and the copy in a project is the one belonging to the
  version that wrote it — so the editor helps with no network, the project
  stays movable, and there is no URL anywhere that has to keep resolving for
  this to work.
- `mela-letterhead schema` writes that copy into a project. `init` already
  does; this is for the two cases it cannot serve — a project made before the
  schema existed, which is also told the one line to add, and a project whose
  copy is a release behind after an upgrade. `check` says so when it finds one
  of those, without failing over it: a schema is the editor's business and
  changes nothing about the page.
- The schema is generated from `DEFAULT_CONFIG` by `tools/generate_schema.py`
  and committed inside the package, so nobody needs the generator to get it.
  Its descriptions are the comments in `config.py` — they were already written
  in the register a tooltip wants — and every vocabulary in it is read from the
  module, so a standard added to `PDF_STANDARDS` reaches the schema with no
  second edit. A stale copy fails CI and the suite.
- A build now reports what went into it. `BuildResult.inputs` is every file it
  read on the user's disk, in staging order, which is what lets a watch rebuild
  one document out of twenty when one of its pictures changes.
- Documented what it takes to get the same bytes out of the same source:
  `SOURCE_DATE_EPOCH`, which Typst reads from the environment it is handed.
  Nothing in the tool had to change — the environment already passed through —
  but an archival PDF that differs between two builds of one document is an
  awkward thing to defend, so it is written down beside `pdf.standard` and
  tested.

## [0.4.0] — 2026-09-20

### Added

- **`pdf.standard`: a PDF you can file.** Until now the tool wrote a generic
  PDF 1.7, which is fine for a letter and not enough for a document that has to
  be filed with a public administration or kept as a record. Set
  `pdf.standard: a-3b` and what comes out is PDF/A — every font embedded,
  nothing fetched from outside, the same document in ten years as today. Set
  `[a-3b, ua-1]` and it is tagged for a screen reader as well. Every standard
  Typst enforces is accepted: the four PDF/A parts at each of their conformance
  levels, PDF/UA-1, and a bare PDF version. The conformance is enforced rather
  than asserted — a document that would not hold up is refused instead of
  written.
- The scaffold builds to PDF/UA-1 with nothing edited, which is the test that
  the two changes below are real rather than nominal.

### Changed

- The footer band stops linking when `ua-1` is asked for. A band is drawn as a
  page artifact — furniture, not content — and PDF/UA-1 allows no link inside
  one, so the e-mail address and anything given a `link:` print as the plain
  text they always were. Nothing reflows; the underline goes with the target,
  since an underline that is not a link is a lie about the page. This is
  settled where the letterhead is resolved, so the Typst module never learns
  that a standard was asked for.
- The two drawings the example document sets side by side now carry
  descriptions, and the paragraph beneath them says why: what goes in the
  square brackets is a caption when a picture stands alone in its paragraph,
  and a description read aloud in place of the picture in every case. The
  scaffold asked for neither before, and was the reason its own pages could not
  be made accessible.
- A version string is read however many components it has. Pandoc numbers its
  releases with four, and the fourth is not decoration here: the Typst writer
  learnt to carry a picture's description in 3.9.0.1, and a pattern that
  stopped at three read that as 3.9.0 and would have called the release too old
  for its own feature.

### Fixed

- Two things that would have been reported as the document's fault are now
  reported as what they are, before the compiler ever sees the document:

  - An accessible standard asked of a Pandoc older than 3.9.0.1, which drops a
    picture's description on its way to the page. Nothing fails; the
    description simply never arrives, and the document is then refused for
    missing what it plainly has. `check` says so, naming both versions.
  - A misspelled standard, which reached the user as a complaint about a
    command-line flag nobody typed. It is now refused where it was written,
    with the nearest name that exists.

  Which standards may be combined is deliberately not checked here. That is a
  question about PDF versions that Typst answers precisely — `a-4` and `ua-1`
  as having no overlapping version, two PDF/A parts as one too many — and a
  second copy of that table would be one to keep in step with a compiler still
  gaining entries. What Typst cannot say is where the request came from, so the
  setting and the file are named alongside whatever it said.

- A document refused for want of alt text now names the pictures that lack it.
  Typst reports `missing alt text` without saying which picture, which in a
  document carrying a dozen of them is the start of a search rather than the
  end of one.

## [0.3.3] — 2026-09-20

### Changed

- **Python 3.10 is the floor.** 3.9 went out of support in October 2025 and the
  tooling has started to follow: mypy needs 3.10 to run, so a developer on the
  old floor could only install a checker a version behind the one CI installed —
  and the newer one, finding a `python_version` it no longer understood, warned
  and then checked against its own interpreter instead. The gate went on passing
  while it had quietly stopped testing the version the package claimed to
  support. Nothing about a letterhead changes; if you are on 3.9, 0.3.2 remains
  installable and works. The annotations throughout the package moved to the
  spellings the new floor allows — `dict[str, Any]`, `str | None` — which is
  why the diff for this release is larger than what it does.
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

[Unreleased]: https://github.com/melasistema/mela-letterhead/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/melasistema/mela-letterhead/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/melasistema/mela-letterhead/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/melasistema/mela-letterhead/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/melasistema/mela-letterhead/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/melasistema/mela-letterhead/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/melasistema/mela-letterhead/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/melasistema/mela-letterhead/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/melasistema/mela-letterhead/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/melasistema/mela-letterhead/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/melasistema/mela-letterhead/releases/tag/v0.2.0
