# Contributing

Thank you for looking. This is a small tool with a clear shape, and most of
what follows is about keeping that shape rather than about process.

## Getting set up

```bash
git clone https://github.com/melasistema/mela-letterhead.git
cd mela-letterhead

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

git config core.hooksPath .githooks   # once per clone; see "Commits" below
```

Then:

```bash
pytest                       # the whole suite
pytest tests/test_config.py  # one file
pytest -k footer_pages       # one test by name

ruff check src tests         # what CI lints
mypy                         # strict, against Python 3.9
```

`tests/test_build.py` shells out to the real Pandoc and the real Typst, and
skips itself when either is missing — so the rest of the suite runs without the
toolchain installed. If those tests silently skip, that is why.

`ruff format` is deliberately **not** run over this project. The prose in the
comments and docstrings is wrapped by hand, much shorter than the 100 columns
the formatter would fill, and unwrapping it would take the shape out of it.
`ruff check` enforces the line limit; how a line gets under it is a judgement.

## The one rule that shapes everything

**All resolution happens in Python.** `assets/letterhead.typ` receives a
finished `document.json` with one language already chosen and every length
already a number of points. It contains no brand, no language and no document,
which is why it never needs editing to print somebody else's paper.

Two things follow:

- JSON has no length type, so lengths cross as bare numbers of points and
  `letterhead.typ`'s `len()` / `em-of()` helpers multiply them back.
- Anything that can go wrong is caught in `config.py`, where the offending
  setting can still be named — not in Typst, where it surfaces as a type error
  about a dictionary.

When you add a feature, resolve it in `config.py` and let Typst read a plain
value. Do not push conditionals into the Typst module.

## A new setting needs three edits

`DEFAULT_CONFIG` in `config.py` *is* the schema. A user's file is deep-merged
onto it and anything not in it is refused by name, with a suggestion. So:

1. an entry in `DEFAULT_CONFIG`, with a comment saying what it is for — or the
   setting is rejected as unknown;
2. a line in the matching `_resolve_*` function, turning what a human wrote
   into what a program consumes;
3. a read in `assets/letterhead.typ`.

And a test. Settings are cheap to add and expensive to remove, so a new one
should be one somebody asked for.

You do not have to think about the name. A section owns its own key names, so
`page.margin: { top: 30mm }` is a margin and `header: { ink: "#fff" }` is a
header, however much `top` and `ink` look like language tags. The exception is
the record vocabulary inside `items:` and `columns:` — `key`, `label`, `value`,
`link`, `style`, `title`, `rows`, `items` — where the schema describes nothing
and shape is all there is to go on. Add a key to one of *those* records and it
belongs in `i18n._RESERVED_KEYS`.

## Traps worth knowing before you hit them

- **`on:` in YAML 1.1 is the boolean `true`.** This is why the footer setting
  is `footer.pages: last` and never `footer.on: last`. Watch for it in any new
  key — `off`, `yes`, `no`, `y` and `n` too.
- **Pandoc's Typst writer renames its helpers between releases.** Debian and
  Ubuntu ship Pandoc 3.1, which emits `#blockquote[…]` where 3.11 emits
  `#quote(block: true)[…]`. `assets/pandoc-typst.template` polyfills the older
  names onto the newer ones, and CI installs apt's Pandoc on purpose so that
  combination stays tested. Anything new the writer may emit belongs in the
  template, not in `letterhead.typ`, which should see one spelling only.
- **Pictures are staged after Pandoc, not before.** Pandoc is what says which
  files a document actually uses. A new way of referring to a picture needs
  nothing in `builder` as long as Pandoc still emits an `image()` call.
- **The scaffold's brand is fictional on purpose** (Acme Studio, `*.example`,
  placeholder VAT and IBAN). This repository is public. Never put real business
  details — a VAT number, a codice fiscale, a PEC address, an IBAN — into
  examples, tests, screenshots or documentation.
- **Code, comments, tests and documentation are in English.** Only the text
  that appears on a user's letterhead is translated.
- **Every file a user edits by hand is read through `yaml_loader.load`.** Not
  `yaml.safe_load`: YAML's rule is that the last of two keys spelled the same
  way wins, which turned a setting written twice into a page nobody asked for
  out of a file `check` called clean. The loader refuses a repeat and names
  both lines. A new place that reads YAML belongs on it too.
- **Not every character the command prints can be printed.** Windows gives a
  redirected command the ANSI code page rather than UTF-8, and there is no tick
  in cp1252 — printing one used to end `check` in a `UnicodeEncodeError` on the
  first line of its own report. A new mark goes through `cli._mark`, which
  takes the spelling the stream can carry and an ASCII one of the same width;
  plain prose stays inside Latin-1, where an em dash and an ellipsis are safe.
  The Windows CI job deliberately does not set `PYTHONUTF8`, so it keeps
  testing the code page rather than stepping around it.

## The schema version

`letterhead.yaml` carries a `version:` key, and `config.load` refuses a file
that declares a version higher than the release understands. Today that number
is 1 and there has never been a 2. The policy for when there is one:

**What forces a bump is a change that would *misread* an existing file** — a
key whose meaning changes, a value that used to mean one thing and now means
another, a default that moves far enough to change a page that was correct.
Adding a key does not force a bump; nor does adding a value a key will accept,
or fixing a resolution that was plainly wrong. An old file that still means
what it said keeps its version.

**A bump ships with a migration.** Version 2 arrives together with a function
in `config.py` keyed by the version written in the file, which turns a version
1 document into a version 2 one in memory. The user's file is never rewritten
on disk; the tool reads what is there and understands it. A release that can
only say "this is too old" is a release that broke somebody's letterhead.

**The error names the release.** A file from the future — version 3 met by a
tool that understands 2 — is refused with the version it saw, the version this
release understands, and what to do about it. That message is the only thing
the user has; it should not make them go and read the changelog.

## Commits

Conventional Commits, enforced by `.githooks/commit-msg` and by CI on every
pull request:

```
type(optional scope): subject
```

| type | means | lands under |
| --- | --- | --- |
| `feat` | a new capability | Added |
| `fix` | a defect repaired | Fixed |
| `perf` | the same result, faster | Changed |
| `refactor` | no change in behaviour | Changed |
| `style` | whitespace, formatting | Changed |
| `docs` | documentation only | Changed |
| `revert` | an earlier commit undone | Removed |
| `build`, `chore`, `ci`, `test` | usually nothing the changelog records | — |

The scope is optional and names the part of the tool the commit touches:
`config`, `i18n`, `builder`, `page`, `footer`, `images`, `brand`, `cli`,
`template`. It is one token — letters, digits, `.`, `_`, `/`, `-` — with no
spaces in it.

Append `!` before the colon, or write `BREAKING CHANGE:` in the body, for a
change that makes an existing `letterhead.yaml` stop working.

```
feat(footer): print a row per column, not per line
fix(config): name the setting a bad length came from
feat(page)!: read background paths relative to the configuration
```

Nothing reads these automatically. What the convention buys is the other
direction: at release time `git log <last tag>..HEAD --oneline` is the list of
what has to be accounted for, already sorted into the sections it will be
written under.

## The changelog

Keep `## [Unreleased]` in `CHANGELOG.md` up to date as you go, in prose, in the
same register as the entries around it: what changed, and what it means for
somebody using the tool — not what the commit did. That section is promoted
verbatim into the release notes, so it is written once and read twice.

## Releasing

Maintainers only, and one command:

```bash
./release.sh --dry-run    # what it would do
./release.sh              # do it
```

It proposes a version from the commits, does the five edits the version lives
in, runs the checks the release workflow runs, and commits and tags. Nothing
leaves the machine until you push the tag — which cuts the GitHub release and
publishes to PyPI. PyPI will not take the same version twice, so the tag is the
point of no return.
