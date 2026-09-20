"""Reading ``letterhead.yaml`` and turning it into what Typst consumes.

There are two shapes of configuration in this module, and keeping them apart is
the point of the file.

The **written** shape is what a user edits: lengths with units (``22mm``),
strings that may be language maps, optional keys everywhere, shorthands for
footer rows. It is forgiving, because a human maintains it.

The **resolved** shape is what :func:`resolve` produces and the Typst module
reads: one language chosen, every length a number of points, every optional key
present, every shorthand expanded. It is rigid, because a program consumes it.

Everything that can go wrong — an unknown page size, a colour that isn't one, a
footer row of the wrong shape — is caught here, where the offending line can
still be named, rather than in Typst, where it would surface as a type error
about a dictionary.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from . import i18n, units, yaml_loader
from .errors import ConfigError

if TYPE_CHECKING:  # `document` imports this module, so the name is only a name
    from .document import Document

CONFIG_FILENAME = "letterhead.yaml"

#: Alternative names accepted when looking for a project's configuration.
CONFIG_FILENAMES = (CONFIG_FILENAME, "letterhead.yml", ".letterhead.yaml")

#: The written shape, with every default filled in. A user's file is merged on
#: top of this, key by key, so a configuration may be as short as a brand name.
DEFAULT_CONFIG: dict[str, Any] = {
    # Schema version. Bumped only for a change that would misread an old file.
    "version": 1,
    # Language used by documents that declare none of their own.
    "language": "en",
    "brand": {
        "name": "",
        # Path to a logo, relative to the configuration file. PNG, JPEG and SVG
        # all work. Leave it out to set the brand name as a typographic
        # wordmark instead.
        "logo": None,
        # Written into the PDF's metadata. Defaults to the brand name.
        "author": None,
        # How the brand name is set when there is no logo file. Every
        # measurement here is a share of the width the mark occupies
        # (`header.logo.width` on page one), so that the smaller mark in the
        # running header is the same design rather than another one. A length
        # may be written instead and is read as a share of that width.
        "wordmark": {
            "font": None,  # defaults to the display stack
            "size": 0.17,
            "weight": 700,
            # Left out, the wordmark follows the ink of whatever it is printed
            # on: the header band on page one, the paper in the running header.
            # A band dark enough to need a pale wordmark is therefore not a
            # band that loses the mark on page two.
            "color": None,
            "tracking": 0.002,
            "align": "left",
        },
        # A line under the mark on page one — under a logo just as under a
        # wordmark. May be written as a plain string, which is the text, or as
        # the mapping below.
        "tagline": {
            "text": None,
            "font": None,  # defaults to the sans stack
            "size": 0.055,
            "weight": 400,
            "color": None,  # defaults to the header band's muted colour
            "tracking": 0.0,
            "gap": "2.4mm",
        },
    },
    "page": {
        "size": "a4",
        "margin": {
            "x": "22mm",
            # Top margin of the inner pages; the first page is pushed down by
            # the header band automatically.
            "top": "27.5mm",
            # Ordinary bottom margin. The last page gains whatever extra room
            # the footer band needs, also automatically.
            "bottom": "39.5mm",
        },
        # A rule around the paper, on every page. Off at nought width, which is
        # the default: a border is a strong device and not every brand wants
        # one. It is drawn under the bands, so a full-bleed band interrupts it
        # rather than being crossed by it.
        "border": {
            "width": 0,
            "color": None,  # defaults to palette.accent
            # Distance from the edge of the paper.
            "inset": "8mm",
            # "all", one of left/right/top/bottom, "x", "y", "none", or a list
            # of sides.
            "sides": "all",
        },
        # A picture behind everything else. Read relative to this file, like
        # the logo and unlike a picture in the body: it belongs to the
        # letterhead, and no document mentions it.
        #
        # This is what turns the tool around. A designer who already has a
        # sheet — drawn in Illustrator, printed by a printer — exports it,
        # points this at it, sets `header.show` and `footer.show` to false and
        # adjusts the margins, and what comes out is their own paper with
        # Markdown set on it.
        "background": {
            # PNG, JPEG or SVG; 300 dpi for print. Typst places no PDF, so a
            # sheet drawn in a page-layout program has to be exported raster.
            "image": None,
            # "cover" fills the paper and crops what will not fit; "contain"
            # fits the whole picture inside it and leaves the paper showing
            # where the proportions disagree.
            "fit": "cover",
            # "first", "rest" (every page but the first) or "all". A designed
            # sheet is usually "first", with a plainer second sheet or none.
            "pages": "first",
            # White laid over the picture, from 0 (none) to 1 (opaque), so
            # that text stays readable over it. Typst has no image opacity,
            # so this really is a translucent white rectangle: it pales a
            # picture on white paper, and does nothing good on any other.
            "veil": 0,
        },
    },
    # The colours of the whole document. Each band may override the ones it
    # uses — see `header.fill` and `footer.fill` — which is what keeps a
    # strongly coloured band from dragging the quotations and the code along
    # with it, since those are drawn on `band` too.
    "palette": {
        "band": "#f5f5f7",  # fill of the header and footer bands
        "rule": "#e6e3ec",  # the thin line along a band's inner edge
        "accent": "#4a3f8a",  # headings, list markers, links
        "ink": "#1c1c20",  # body text
        "muted": "#6f6b74",  # running header, placeholder rules
        "highlight": "#a4262c",  # a footer row that must catch the eye
        "hairline": "#dcd9e2",  # rules between sections and table rows
    },
    "fonts": {
        # Each entry is a fallback stack: the first font installed wins. Typst
        # carries Libertinus Serif, New Computer Modern and DejaVu Sans Mono
        # itself, so the serif and mono stacks resolve on any machine; there is
        # no sans face inside Typst, and the sans stack names the ones that
        # come with macOS, Windows and the common Linux font packages in turn.
        # `mela-letterhead check` reports which one you are actually getting.
        "serif": ["Libertinus Serif", "New Computer Modern"],
        "sans": [
            "Helvetica Neue",
            "Inter",
            "Arial",
            "Liberation Sans",
            "DejaVu Sans",
            "New Computer Modern",
        ],
        # Used for the footer band. Defaults to the serif stack.
        "display": None,
        "mono": ["DejaVu Sans Mono", "Menlo", "Consolas"],
        # Directories of font files to load in addition to the system's.
        "paths": [],
    },
    "typography": {
        "size": "11pt",
        # Leading and spacing are multiples of the font size, so they follow
        # whatever text they are applied to.
        "leading": 0.82,
        "paragraph_spacing": 0.95,
        "justify": True,
        "hyphenate": True,
        "headings": {
            "h1": "15pt",
            "h2": "12.5pt",
            "h3": "10.6pt",
            "h4": "10pt",
        },
        "table_size": "9.6pt",
        "quote_size": "9.9pt",
        # Inline code, relative to the surrounding text.
        "code_size": 0.82,
    },
    # Pictures in the body: photographs, drawings, plates of previous work.
    # Their files are read relative to the document that names them.
    "images": {
        # Width of an image that gives none of its own, as a share of the
        # column: "70%", or the fraction 0.7. `auto` prints it at its natural
        # size, shrunk to the column when it is wider — which is the only
        # setting that leaves a small mark small.
        "width": "auto",
        # Where a figure sits in the column. An image without a caption stays
        # inline in the text it was written in, and follows the paragraph.
        "align": "center",
        # A hairline around the image. Worth turning on for artwork that runs
        # pale at the edges, which would otherwise bleed into the paper.
        "frame": False,
        # Number the figures ("Figure 1: ..."). The word is Typst's own and
        # follows the document's language.
        "numbered": False,
        "caption": {
            "size": "9.2pt",
            # Between the image and its caption.
            "gap": "6pt",
        },
    },
    "header": {
        "show": True,
        "height": "43mm",
        # Space between the band and the first line of text on page one.
        "gap": "9.1mm",
        # Thickness of the accent line along the band's lower edge.
        "rule": "3pt",
        # The band's own colours. Each falls back to the palette, so a band is
        # recoloured on its own: `fill` for the ground, `ink` for the fields
        # printed on it, `muted` for the rule drawn where a value is missing,
        # and `rule_color` for the line along the lower edge.
        "fill": None,
        "ink": None,
        "muted": None,
        "rule_color": None,
        "logo": {
            "width": "67mm",
            "y": "11.8mm",  # from the top of the page
        },
        "fields": {
            "y": "9.7mm",
            "align": "right",
            "size": "11.5pt",
            "leading": "7.2pt",
            "label_gap": "4pt",
            # Width of the rule drawn in place of a value left empty.
            "blank_width": "32.5mm",
            # What to do with a field whose value is empty:
            #   rule  — print a line to fill in by hand (the default)
            #   blank — print the label and nothing after it
            #   hide  — leave the field out entirely
            "when_empty": "rule",
            "items": [],
        },
    },
    # The reduced header of every page after the first.
    "running": {
        "show": True,
        "logo_width": "26mm",
        "logo_y": "9.2mm",
        "text_y": "11.1mm",
        "align": "right",
        "size": "8pt",
        "tracking": "0.2pt",
        # Hairline under the running header. Set to 0 to remove it.
        "rule": "0.5pt",
        "rule_y": "19mm",
        # Overrides the locale pack's `running_header`.
        "format": None,
    },
    "footer": {
        "show": True,
        # "last" prints the band on the final page only; "all" on every page.
        # Not spelled `on`, which YAML reads as the boolean true.
        "pages": "last",
        "height": "50.2mm",
        # Clearance between the band and the last line of text above it.
        "gap": "6.9mm",
        "rule": "3pt",
        # As in `header`, with `highlight` for the one row that has to catch
        # the eye. All four fall back to the palette.
        "fill": None,
        "ink": None,
        "muted": None,
        "highlight": None,
        "rule_color": None,
        # Distance from the bottom edge of the page to the band.
        "offset": "0mm",
        "align": "center",
        "title_size": "15pt",
        "size": "11pt",
        # Air between the rows of a column. Kept in the same proportion to the
        # text as the header fields' own leading is to theirs, so both blocks
        # of detail read alike; the band centres its content, so a taller
        # column simply eats into the space above and below it.
        "leading": "6.9pt",
        "title_gap": "6pt",
        # Gutter between columns.
        "gutter": "40pt",
        "columns": [],
    },
    "markdown": {
        # Passed to Pandoc as --from. Add +hard_line_breaks if you write one
        # sentence per line and want every one of those breaks on paper; with
        # it, a paragraph wrapped at 80 columns prints wrapped at 80 columns.
        "format": "markdown",
        # Recompute table column widths from the content. Pandoc derives Typst
        # column widths from the number of dashes in the separator row, so
        # `|---|---:|` would otherwise give a one-word column half the page.
        "rewrite_table_widths": True,
        # Drop `---` rules: the hierarchy is already carried by the rules above
        # headings, and a full-width line on top of that reads as heavy.
        "drop_horizontal_rules": True,
        # Set the header row of a table in bold, so it needs no Typst rule that
        # would also catch tables that have no header.
        "bold_table_header": True,
        # Extra arguments appended to the Pandoc invocation.
        "extra_args": [],
    },
    "pdf": {
        # The standards the PDF must conform to, as a name or a list of them.
        # Empty is an ordinary PDF, which is what a letter is.
        #
        # A document filed with a public administration or kept as a record is
        # usually asked for as PDF/A — `a-2b` and `a-3b` are the common ones —
        # and one that has to be readable by assistive technology as PDF/UA-1.
        # `a-2b` and `ua-1` may be asked for together; `a-4` and `ua-1` may not,
        # because one is PDF 2.0 and the other PDF 1.7.
        #
        # Typst enforces conformance and refuses what cannot be combined; this
        # setting only carries the request to it. See `pdf.standard` in the
        # README for what each one demands of a document.
        "standard": [],
    },
    "documents": {
        "source": ".",
        "output": ".",
        "include": ["*.md"],
        "exclude": ["README.md", "CHANGELOG.md", "LICENSE.md"],
        # YAML reads an unquoted `date: 2026-09-14` as a date, not a string.
        # This is how such a value is printed. Quote the value in the front
        # matter instead to write it exactly as you want it.
        "date_format": "%Y-%m-%d",
    },
    # Intermediates live here. Safe to delete, and worth reading when a
    # document does not come out the way you expected.
    "build_dir": ".letterhead-build",
}

_ALIGNMENTS = ("left", "center", "right")

#: Typst's named font weights, accepted wherever a number from 100 to 900 is.
_FONT_WEIGHTS = (
    "thin",
    "extralight",
    "light",
    "regular",
    "medium",
    "semibold",
    "bold",
    "extrabold",
    "black",
)

#: How a page background may be fitted to the paper, and where it may be drawn.
_BACKGROUND_FITS = ("cover", "contain")
_BACKGROUND_PAGES = ("first", "rest", "all")

#: Which pages carry the footer band. Not spelled `on`, which YAML reads as the
#: boolean true.
_FOOTER_PAGES = ("last", "all")

#: What becomes of a header field whose value is empty: a line to fill in by
#: hand, the label alone, or nothing at all.
_WHEN_EMPTY = ("rule", "blank", "hide")

#: How a footer row is set.
_ROW_STYLES = ("normal", "highlight", "muted")

#: What each name for a border's sides expands to.
_BORDER_SIDES: dict[str, tuple[str, ...]] = {
    "all": ("left", "right", "top", "bottom"),
    "none": (),
    "left": ("left",),
    "right": ("right",),
    "top": ("top",),
    "bottom": ("bottom",),
    "x": ("left", "right"),
    "y": ("top", "bottom"),
}

#: The PDF standards `pdf.standard` accepts, which are the ones Typst enforces.
#: Each is a PDF version, a PDF/A part and conformance level, or PDF/UA-1.
#:
#: Only the names are checked here, and deliberately not the combinations. Which
#: of these may be asked for together is a question about PDF versions that the
#: ISO standards settle and Typst already answers precisely — `a-4` and `ua-1`
#: are refused as having no overlapping version, two PDF/A parts as one too
#: many. Restating that here would be a second copy of a table to keep in step
#: with a compiler that is still gaining entries. A name, though, is worth
#: catching: mistype one and the error comes from a command-line flag nobody
#: typed, naming neither this setting nor the file it is written in.
PDF_STANDARDS = (
    "1.4",
    "1.5",
    "1.6",
    "1.7",
    "2.0",
    "a-1b",
    "a-1a",
    "a-2b",
    "a-2u",
    "a-2a",
    "a-3b",
    "a-3u",
    "a-3a",
    "a-4",
    "a-4f",
    "a-4e",
    "ua-1",
)

#: The standards that require every picture to carry a description. These are
#: the accessible ones: PDF/UA-1, and the `a` conformance level of each PDF/A
#: part, which is the level that adds the accessibility requirements to it.
#: Measured against Typst 0.15: the `b` and `u` levels compile the scaffold
#: without complaint, and these four refuse it.
PDF_STANDARDS_NEEDING_ALT_TEXT = frozenset({"a-1a", "a-2a", "a-3a", "ua-1"})


class Config:
    """A loaded configuration, together with where it came from.

    ``directory`` is what every relative path in the file resolves against, so
    a configuration can be used from any working directory.

    ``profiles`` is held apart from ``data`` rather than inside it, and
    :func:`load` is where the difference is argued.
    """

    def __init__(
        self,
        data: dict[str, Any],
        path: Path | None,
        profiles: dict[str, Any] | None = None,
    ) -> None:
        self.data = data
        self.path = path
        self.profiles = profiles or {}
        self.directory = path.parent.resolve() if path else Path.cwd()

    # -- paths ------------------------------------------------------------

    def resolve_path(self, value: str) -> Path:
        """Resolve a path written in the configuration against its directory."""
        candidate = Path(value).expanduser()
        return candidate if candidate.is_absolute() else self.directory / candidate

    @property
    def build_dir(self) -> Path:
        return self.resolve_path(str(self.data["build_dir"]))

    @property
    def source_dir(self) -> Path:
        return self.resolve_path(str(self.data["documents"]["source"]))

    @property
    def output_dir(self) -> Path:
        return self.resolve_path(str(self.data["documents"]["output"]))

    @property
    def locales_dir(self) -> Path:
        return self.directory / "locales"

    @property
    def default_language(self) -> str:
        return str(self.data.get("language") or i18n.DEFAULT_LANGUAGE)


def find_config(start: Path | None = None) -> Path | None:
    """Search ``start`` and its parents for a letterhead configuration."""
    directory = (start or Path.cwd()).resolve()
    for candidate_dir in [directory, *directory.parents]:
        for name in CONFIG_FILENAMES:
            candidate = candidate_dir / name
            if candidate.is_file():
                return candidate
    return None


def load(path: Path | None = None, start: Path | None = None) -> Config:
    """Load a configuration, searching upwards from ``start`` if none is given."""
    if path is None:
        found = find_config(start)
        if found is None:
            raise ConfigError(
                f"no {CONFIG_FILENAME} found in this directory or any above it",
                hint="Run 'mela-letterhead init' to create one.",
            )
        path = found

    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"{path}: no such file")

    try:
        raw = yaml_loader.load(path.read_text(encoding="utf-8"))
    except yaml_loader.DuplicateKeyError as exc:
        raise ConfigError(
            f"{path}: '{exc.key}' is set twice, on line {exc.first_line} "
            f"and on line {exc.second_line}",
            hint=yaml_loader.DUPLICATE_KEY_HINT,
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: {exc.strerror or exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: the file must contain a mapping at the top level")

    # Taken out before anything else runs, and this is not tidiness. Left in,
    # `_deep_merge` would merge a profile *into* the schema, which is the
    # opposite of what a profile is; `_reject_unknown_keys` would refuse every
    # profile name as an unknown setting; and `is_translation` against an empty
    # schema node falls through to shape alone, so `profiles: { de:, it: }` —
    # a natural way to name profiles — would be read as a translation *of*
    # `profiles` and collapsed to one of them by `localise`. Popping it here
    # makes all three impossible rather than guarded against.
    profiles = _profiles(raw.pop("profiles", None), path)

    version = raw.get("version", DEFAULT_CONFIG["version"])
    if isinstance(version, int) and version > DEFAULT_CONFIG["version"]:
        raise ConfigError(
            f"{path}: this file declares version {version}, but this release "
            f"understands up to version {DEFAULT_CONFIG['version']}",
            hint="Upgrade mela-letterhead, or lower the 'version' key.",
        )

    merged = _deep_merge(copy.deepcopy(DEFAULT_CONFIG), raw)
    _reject_unknown_keys(merged, DEFAULT_CONFIG, path)
    return Config(merged, path, profiles)


def _profiles(written: Any, path: Path) -> dict[str, Any]:
    """Check the shape of ``profiles:`` and nothing else.

    The names are the user's, so there is nothing to suggest against. What is
    *in* a profile is checked when the profile is applied, which is the moment
    an error can name both the profile and the setting.
    """
    if written is None:
        return {}
    if not isinstance(written, dict):
        raise ConfigError(
            f"{path}: 'profiles' must be a mapping of names to settings",
            hint="Each name holds the settings that profile changes:\n"
            "  profiles:\n"
            "    draft:\n"
            "      palette:\n"
            "        accent: '#a4262c'",
        )
    for name, settings in written.items():
        if not isinstance(settings, dict):
            raise ConfigError(
                f"{path}: profiles.{name}: a profile must be a mapping of "
                f"settings, got {settings!r}",
                hint="It is written like the part of letterhead.yaml it "
                "overrides, and may set as little as one colour.",
            )
    return written


def resolve(
    config: Config,
    document: Document,
    language: str,
    profile: str | None = None,
) -> dict[str, Any]:
    """Produce the resolved configuration for one document in one language.

    The document supplies the values of the header fields and its own title.

    The written shape has three sources, lowest first: the file itself, the
    active profile, and the document's own ``letterhead:`` block. They are
    merged here — not in :func:`load`, because both of the upper two are
    per-document, and not in the builder, because ``check`` and ``build`` both
    come through this function and anything merged elsewhere would give them
    different answers.
    """
    chain = i18n.fallback_chain(language, config.default_language)
    strings = i18n.load_locale(chain, config.locales_dir)

    # Merged in the written shape, and localised once at the end. This ordering
    # is the one thing here that a later change could quietly break: merge
    # after localising and a translated override becomes impossible, because
    # `letterhead: { brand: { tagline: { de: "…" } } }` has to reach `localise`
    # as a language map rather than as a string somebody already chose. It
    # would pass every test that does not use two languages.
    data = copy.deepcopy(config.data)
    for override, where, prefix in _overrides(config, document, profile):
        _reject_unknown_keys(override, DEFAULT_CONFIG, where, prefix)
        _deep_merge(data, override)
    data = i18n.localise(data, chain, DEFAULT_CONFIG)

    width, height = units.page_size(data["page"]["size"], "page.size")
    margin = data["page"]["margin"]
    margin_x = units.to_points(margin["x"], "page.margin.x")
    margin_top = units.to_points(margin["top"], "page.margin.top")
    margin_bottom = units.to_points(margin["bottom"], "page.margin.bottom")

    # Resolved first: the bands and the border may each name a colour of their
    # own, and fall back to the palette when they do not.
    palette = {
        key: units.to_colour(value, f"palette.{key}")
        for key, value in data["palette"].items()
    }
    fonts = resolve_fonts(data["fonts"])

    pdf = _resolve_pdf(data["pdf"])

    header = _resolve_header(data["header"], document, palette)
    running = _resolve_running(data["running"], strings, data["brand"], document)
    # The footer band is the one place in the letterhead that can carry a link,
    # and PDF/UA-1 does not allow one there. Settled here rather than in Typst,
    # which never learns that a standard was asked for.
    footer = _resolve_footer(data["footer"], palette, links="ua-1" not in pdf["standard"])

    # The first page starts below the header band; the inner pages keep the
    # ordinary top margin. Typst has one top margin per page, so the difference
    # is inserted as vertical space at the head of the body.
    first_page_extra = 0.0
    if header["show"]:
        first_page_extra = max(0.0, header["height"] + header["gap"] - margin_top)

    # A footer on every page has to be reserved in the margin; a footer on the
    # last page only is reserved by a block at the end of the body, so the
    # inner pages keep their full text height.
    footer_reserve = 0.0
    if footer["show"]:
        needed = footer["height"] + footer["offset"] + footer["gap"]
        if footer["pages"] == "all":
            margin_bottom = max(margin_bottom, needed)
        else:
            footer_reserve = max(0.0, needed - margin_bottom)

    lang, region = i18n.split_tag(language)

    brand = data["brand"]
    title = document.title or strings.get("untitled", "Untitled document")

    # The wordmark is measured against the slot the mark occupies on page one,
    # which the running header then scales down as a whole.
    mark_width = header["logo"]["width"]

    return {
        "brand": {
            "name": brand.get("name") or "",
            # The path as written, with a language map already collapsed. The
            # builder replaces it with the name the file landed under in the
            # build directory.
            "logo": _as_text(brand.get("logo")) or None,
            "wordmark": _resolve_wordmark(
                brand["wordmark"], fonts, palette, mark_width, header["ink"]
            ),
            "tagline": _resolve_tagline(
                brand["tagline"], fonts, mark_width, header["muted"]
            ),
        },
        "document": {
            "title": title,
            "author": brand.get("author") or brand.get("name") or "",
            "lang": lang,
            "region": region,
        },
        "page": {
            "width": width,
            "height": height,
            "margin": {"x": margin_x, "top": margin_top, "bottom": margin_bottom},
            "first_page_extra": first_page_extra,
            "footer_reserve": footer_reserve,
            "border": _resolve_border(data["page"]["border"], palette),
            "background": _resolve_background(data["page"]["background"]),
        },
        "palette": palette,
        "pdf": pdf,
        "fonts": fonts,
        "typography": _resolve_typography(data["typography"]),
        "images": _resolve_images(data["images"]),
        "header": header,
        "running": running,
        "footer": footer,
    }


# ---------------------------------------------------------------------------
# overrides: the profile, and the document's own block
# ---------------------------------------------------------------------------


def _overrides(
    config: Config, document: Document, requested: str | None
) -> list[tuple[dict[str, Any], Path, str]]:
    """What is merged onto the letterhead, in ascending order of precedence.

    Each entry carries where it was written, so that a setting the schema does
    not know is refused by the name it was given: ``profiles.draft.palete``
    rather than ``palete``.
    """
    overrides: list[tuple[dict[str, Any], Path, str]] = []

    name, settings = _active_profile(config, document, requested)
    if name is not None:
        where = config.path or Path(CONFIG_FILENAME)
        overrides.append((settings, where, f"profiles.{name}."))

    block = document.overrides
    if block:
        overrides.append((block, document.path, "letterhead."))
    return overrides


def _active_profile(
    config: Config, document: Document, requested: str | None
) -> tuple[str | None, dict[str, Any]]:
    """Which profile applies, and what is in it.

    The flag wins for the whole run; a document's own ``profile:`` is its
    default. ``build --profile draft`` is a thing typed one second ago about
    this run, and its main use — watermarking everything on the way out — is
    exactly the one a per-document veto would break. Front matter is where a
    document that is *always* a draft says so.
    """
    name = requested or document.profile
    if name is None:
        return None, {}

    if name not in config.profiles:
        known = ", ".join(sorted(config.profiles))
        suggestion = _closest(name, list(config.profiles))
        # Silently ignoring a mistyped name is how a draft reaches a client.
        raise ConfigError(
            f"unknown profile {name!r}",
            hint=(f"Did you mean '{suggestion}'? " if suggestion else "")
            + (
                f"Known profiles: {known}."
                if known
                else f"No profiles are defined in {CONFIG_FILENAME}."
            ),
        )
    settings = config.profiles[name]
    return name, settings


def count_settings(override: dict[str, Any], schema: Any = None) -> int:
    """How many settings an override actually changes.

    A section counts as the settings inside it and a translation as the one
    setting it translates, so ``{ palette: { accent:, ink: } }`` is two and
    ``{ brand: { tagline: { en:, de: } } }`` is one. Public because ``check``
    is the place this has to be visible: an override silently not applied is
    the failure this feature will have.
    """
    if schema is None:
        schema = DEFAULT_CONFIG
    total = 0
    for key, value in override.items():
        node = schema.get(key) if isinstance(schema, dict) else None
        if (
            isinstance(value, dict)
            and isinstance(node, dict)
            and node
            and not i18n.is_translation(value, node)
        ):
            total += count_settings(value, node)
        else:
            total += 1
    return total


# ---------------------------------------------------------------------------
# section resolvers
# ---------------------------------------------------------------------------


def resolve_fonts(fonts: dict[str, Any]) -> dict[str, Any]:
    default = DEFAULT_CONFIG["fonts"]
    serif = _font_stack(fonts.get("serif"), "fonts.serif", default["serif"])
    sans = _font_stack(fonts.get("sans"), "fonts.sans", default["sans"])
    return {
        "serif": serif,
        "sans": sans,
        "display": _font_stack(fonts.get("display"), "fonts.display", serif),
        "mono": _font_stack(fonts.get("mono"), "fonts.mono", default["mono"]),
    }


def _font_stack(value: Any, field: str, fallback: list[str] | None = None) -> list[str]:
    """One font name or a fallback stack of them, however it was written."""
    if value is None:
        if fallback is None:
            raise ConfigError(f"{field}: no font given and no fallback")
        return list(fallback)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        if not value:
            raise ConfigError(f"{field}: the font stack is empty")
        return list(value)
    raise ConfigError(f"{field}: expected a font name or a list of them, got {value!r}")


def _resolve_wordmark(
    wordmark: dict[str, Any],
    fonts: dict[str, Any],
    palette: dict[str, str],
    mark_width: float,
    band_ink: str,
) -> dict[str, Any]:
    """How the brand name is set when there is no logo file.

    A letterhead with nothing but a name on it is a letterhead, and for a great
    many people it is the right one — so the name gets the same settings a logo
    would have had, rather than one hard-coded style.

    The mark prints on two grounds — the header band on page one, bare paper in
    the running header — so it resolves to two colours. A wordmark left to
    follow the band would otherwise vanish on page two the moment the band was
    darkened; one given a colour of its own keeps it in both places.
    """
    written = wordmark["color"]
    return {
        "font": _font_stack(wordmark["font"], "brand.wordmark.font", fonts["display"]),
        "size": units.to_share(wordmark["size"], "brand.wordmark.size", mark_width),
        "weight": _weight(wordmark["weight"], "brand.wordmark.weight"),
        "color": _colour_or(written, "brand.wordmark.color", band_ink),
        "running_color": _colour_or(written, "brand.wordmark.color", palette["ink"]),
        "tracking": units.to_share(
            wordmark["tracking"], "brand.wordmark.tracking", mark_width, positive=False
        ),
        "align": _alignment(wordmark["align"], "brand.wordmark.align"),
    }


def _resolve_tagline(
    tagline: Any,
    fonts: dict[str, Any],
    mark_width: float,
    band_muted: str,
) -> dict[str, Any]:
    """The line under the mark, written either as a string or in full.

    It prints on page one only, so unlike the wordmark it needs one colour, and
    that colour follows the header band.
    """
    if isinstance(tagline, str) or tagline is None:
        written = dict(DEFAULT_CONFIG["brand"]["tagline"])
        written["text"] = tagline or None
    elif isinstance(tagline, dict):
        written = tagline
    else:
        raise ConfigError(
            f"brand.tagline: expected a line of text, got {tagline!r}",
            hint="Write it as text — tagline: Graphic design, Milan — or as a "
            "mapping with 'text' and the styling beside it.",
        )

    text = written.get("text")
    if text is not None and not isinstance(text, str):
        text = str(text)
    if text is not None and not text.strip():
        text = None

    return {
        "text": text,
        "font": _font_stack(written["font"], "brand.tagline.font", fonts["sans"]),
        "size": units.to_share(written["size"], "brand.tagline.size", mark_width),
        "weight": _weight(written["weight"], "brand.tagline.weight"),
        "color": _colour_or(written["color"], "brand.tagline.color", band_muted),
        "tracking": units.to_share(
            written["tracking"], "brand.tagline.tracking", mark_width, positive=False
        ),
        # Negative on purpose where it is asked for: a mark with optical
        # whitespace under it needs the line pulled back up into it.
        "gap": units.to_points(written["gap"], "brand.tagline.gap", positive=False),
    }


def _resolve_border(border: dict[str, Any], palette: dict[str, str]) -> dict[str, Any]:
    """The rule around the paper, and which of its four sides are drawn."""
    return {
        "width": units.to_points(border["width"], "page.border.width"),
        "color": _colour_or(border["color"], "page.border.color", palette["accent"]),
        "inset": units.to_points(border["inset"], "page.border.inset"),
        "sides": _sides(border["sides"], "page.border.sides"),
    }


def _resolve_background(background: dict[str, Any]) -> dict[str, Any]:
    """The picture behind the page, and where it is drawn.

    The file itself is not opened here — like the logo it is staged into the
    build directory, and the builder writes back the name it landed under.
    Everything else about it is settled now, so that Typst is handed a fit it
    can use and a page test it can answer with an integer.
    """
    fit = str(background["fit"]).lower()
    if fit not in _BACKGROUND_FITS:
        raise ConfigError(
            f"page.background.fit: expected {' or '.join(_BACKGROUND_FITS)}, "
            f"got {background['fit']!r}",
            hint="'cover' fills the paper and crops what will not fit; "
            "'contain' fits the whole picture inside it.",
        )

    pages = str(background["pages"]).lower()
    if pages not in _BACKGROUND_PAGES:
        raise ConfigError(
            f"page.background.pages: expected one of "
            f"{', '.join(_BACKGROUND_PAGES)}, got {background['pages']!r}",
            hint="'first' prints it on the first page only, 'rest' on every "
            "page after it, 'all' on all of them.",
        )

    return {
        # As written, with a language map already collapsed — a brand with a
        # sheet per market has one per market here too. Replaced by the
        # builder with the staged name.
        "image": _as_text(background["image"]) or None,
        "fit": fit,
        "pages": pages,
        "veil": units.to_alpha(background["veil"], "page.background.veil"),
    }


def _resolve_typography(typography: dict[str, Any]) -> dict[str, Any]:
    headings = typography.get("headings") or {}
    return {
        "size": units.to_points(typography["size"], "typography.size"),
        "leading": units.to_em(typography["leading"], "typography.leading"),
        "paragraph_spacing": units.to_em(
            typography["paragraph_spacing"], "typography.paragraph_spacing"
        ),
        "justify": bool(typography["justify"]),
        "hyphenate": bool(typography["hyphenate"]),
        "headings": {
            level: units.to_points(
                headings.get(level, DEFAULT_CONFIG["typography"]["headings"][level]),
                f"typography.headings.{level}",
            )
            for level in ("h1", "h2", "h3", "h4")
        },
        "table_size": units.to_points(typography["table_size"], "typography.table_size"),
        "quote_size": units.to_points(typography["quote_size"], "typography.quote_size"),
        "code_size": units.to_em(typography["code_size"], "typography.code_size"),
    }


def _resolve_images(images: dict[str, Any]) -> dict[str, Any]:
    width = images["width"]
    if isinstance(width, str) and width.strip().lower() in ("auto", "natural"):
        # None, rather than 1.0: an image with no width of its own is left at
        # its natural size, which is not the same as one filling the column.
        width = None
    elif width is not None:
        width = units.to_ratio(width, "images.width")

    caption = images["caption"]
    return {
        "width": width,
        "align": _alignment(images["align"], "images.align"),
        "frame": bool(images["frame"]),
        "numbered": bool(images["numbered"]),
        "caption": {
            "size": units.to_points(caption["size"], "images.caption.size"),
            "gap": units.to_points(caption["gap"], "images.caption.gap"),
        },
    }


def _resolve_header(
    header: dict[str, Any], document: Any, palette: dict[str, str]
) -> dict[str, Any]:
    fields = header["fields"]
    when_empty = str(fields.get("when_empty", "rule")).lower()
    if when_empty not in _WHEN_EMPTY:
        raise ConfigError(
            f"header.fields.when_empty: expected {_one_of(_WHEN_EMPTY)}, "
            f"got {fields['when_empty']!r}"
        )

    items: list[dict[str, Any]] = []
    for index, item in enumerate(fields.get("items") or []):
        where = f"header.fields.items[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(
                f"{where}: expected a mapping with a 'label', got {item!r}",
                hint="Each header field looks like:\n"
                "  - key: reference\n"
                "    label: Reference",
            )
        label = item.get("label")
        if label is not None and not isinstance(label, str):
            raise ConfigError(f"{where}.label: expected a string, got {label!r}")

        # A field takes its value from the document's front matter when it
        # names a key, and from the configuration when it does not — the
        # difference between "Date", which changes per document, and
        # "Department", which does not.
        value = item.get("value")
        key = item.get("key")
        if key is not None:
            if not isinstance(key, str):
                raise ConfigError(f"{where}.key: expected a string, got {key!r}")
            from_document = document.field(key)
            if from_document is not None:
                value = from_document

        if value is not None and not isinstance(value, str):
            value = str(value)
        if value is not None and not value.strip():
            value = None
        if value is None and when_empty == "hide":
            continue

        items.append({"label": label, "value": value})

    return {
        "show": bool(header["show"]),
        "height": units.to_points(header["height"], "header.height"),
        "gap": units.to_points(header["gap"], "header.gap"),
        "rule": units.to_points(header["rule"], "header.rule"),
        "fill": _colour_or(header["fill"], "header.fill", palette["band"]),
        "ink": _colour_or(header["ink"], "header.ink", palette["ink"]),
        "muted": _colour_or(header["muted"], "header.muted", palette["muted"]),
        "rule_color": _colour_or(
            header["rule_color"], "header.rule_color", palette["rule"]
        ),
        "logo": {
            "width": units.to_points(header["logo"]["width"], "header.logo.width"),
            "y": units.to_points(header["logo"]["y"], "header.logo.y"),
        },
        "fields": {
            "y": units.to_points(fields["y"], "header.fields.y"),
            "align": _alignment(fields["align"], "header.fields.align"),
            "size": units.to_points(fields["size"], "header.fields.size"),
            "leading": units.to_points(fields["leading"], "header.fields.leading"),
            "label_gap": units.to_points(fields["label_gap"], "header.fields.label_gap"),
            "blank_width": units.to_points(
                fields["blank_width"], "header.fields.blank_width"
            ),
            "when_empty": when_empty,
            "items": items,
        },
    }


def _resolve_running(
    running: dict[str, Any],
    strings: dict[str, Any],
    brand: dict[str, Any],
    document: Any,
) -> dict[str, Any]:
    template = running.get("format") or strings.get(
        "running_header", "{title} · page {page} of {pages}"
    )
    if not isinstance(template, str):
        raise ConfigError(f"running.format: expected a string, got {template!r}")

    # {title} and {brand} are known now; {page} and {pages} are not known until
    # the document has been laid out, so they travel to Typst as they are.
    text = template.replace("{title}", document.running_title or document.title or "")
    text = text.replace("{brand}", str(brand.get("name") or ""))

    return {
        "show": bool(running["show"]),
        "logo_width": units.to_points(running["logo_width"], "running.logo_width"),
        "logo_y": units.to_points(running["logo_y"], "running.logo_y"),
        "text_y": units.to_points(running["text_y"], "running.text_y"),
        "align": _alignment(running["align"], "running.align"),
        "size": units.to_points(running["size"], "running.size"),
        # Negative tracking is ordinary typography, not a mistake.
        "tracking": units.to_points(running["tracking"], "running.tracking", positive=False),
        "rule": units.to_points(running["rule"], "running.rule"),
        "rule_y": units.to_points(running["rule_y"], "running.rule_y"),
        "text": text,
    }


def _resolve_pdf(pdf: dict[str, Any]) -> dict[str, Any]:
    """Settle ``pdf.standard`` into a list of names, in the order written.

    One name may be written on its own; the list form is for asking a document
    to be both archival and accessible at once, which is the case this setting
    exists for.
    """
    written = pdf.get("standard") or []
    if isinstance(written, str):
        written = [written]
    if not isinstance(written, (list, tuple)):
        raise ConfigError(
            f"pdf.standard: expected a name or a list of names, got {written!r}",
            hint="For example 'a-3b', or [a-3b, ua-1].",
        )

    standards: list[str] = []
    for entry in written:
        if not isinstance(entry, str):
            raise ConfigError(f"pdf.standard: expected a name, got {entry!r}")
        name = entry.strip().lower()
        if name not in PDF_STANDARDS:
            suggestion = _closest(name, list(PDF_STANDARDS))
            known = ", ".join(PDF_STANDARDS)
            raise ConfigError(
                f"pdf.standard: unknown standard {entry!r}",
                hint=(f"Did you mean '{suggestion}'? " if suggestion else "")
                + f"Known standards: {known}.",
            )
        # Written twice is not an error, just nothing: the same request.
        if name not in standards:
            standards.append(name)

    return {"standard": standards}


def _resolve_footer(
    footer: dict[str, Any], palette: dict[str, str], links: bool = True
) -> dict[str, Any]:
    pages = str(footer.get("pages", "last")).lower()
    if pages not in _FOOTER_PAGES:
        raise ConfigError(
            f"footer.pages: expected {_one_of(_FOOTER_PAGES)}, got {footer['pages']!r}",
            hint="'last' prints the band on the final page only; 'all' on every page.",
        )

    columns = []
    for index, column in enumerate(footer.get("columns") or []):
        columns.append(
            _resolve_footer_column(column, f"footer.columns[{index}]", links=links)
        )

    return {
        "show": bool(footer["show"]) and bool(columns),
        "pages": pages,
        "height": units.to_points(footer["height"], "footer.height"),
        "gap": units.to_points(footer["gap"], "footer.gap"),
        "rule": units.to_points(footer["rule"], "footer.rule"),
        "fill": _colour_or(footer["fill"], "footer.fill", palette["band"]),
        "ink": _colour_or(footer["ink"], "footer.ink", palette["ink"]),
        "muted": _colour_or(footer["muted"], "footer.muted", palette["muted"]),
        "highlight": _colour_or(
            footer["highlight"], "footer.highlight", palette["highlight"]
        ),
        "rule_color": _colour_or(
            footer["rule_color"], "footer.rule_color", palette["rule"]
        ),
        # Negative pushes the band off the bottom edge, which is what a design
        # that bleeds past the trim asks for.
        "offset": units.to_points(footer["offset"], "footer.offset", positive=False),
        "align": _alignment(footer["align"], "footer.align"),
        "title_size": units.to_points(footer["title_size"], "footer.title_size"),
        "size": units.to_points(footer["size"], "footer.size"),
        "leading": units.to_points(footer["leading"], "footer.leading"),
        "title_gap": units.to_points(footer["title_gap"], "footer.title_gap"),
        "gutter": units.to_points(footer["gutter"], "footer.gutter"),
        "columns": columns,
    }


def _resolve_footer_column(column: Any, where: str, links: bool = True) -> dict[str, Any]:
    if not isinstance(column, dict):
        raise ConfigError(
            f"{where}: expected a mapping with 'title' and 'rows', got {column!r}"
        )
    title = column.get("title")
    if title is not None and not isinstance(title, str):
        title = str(title)

    rows = []
    for index, row in enumerate(column.get("rows") or []):
        rows.append(_resolve_footer_row(row, f"{where}.rows[{index}]", links=links))
    return {"title": title, "rows": rows}


def _resolve_footer_row(row: Any, where: str, links: bool = True) -> dict[str, Any]:
    """Expand the three ways a footer row may be written.

    ``"Some line"``              a line with no label
    ``["Tel.", "+39 ..."]``      a label and a value
    ``{label:, value:, ...}``    the full form, with ``link`` and ``style``
    """
    # Declared before the branches because each writes something different
    # here: a string, whatever the two-item list held, or whatever the mapping
    # held. `_as_text` below is what settles them into the strings that print.
    label: Any
    value: Any
    link: Any
    style: str

    if isinstance(row, str):
        label, value, link, style = None, row, None, "normal"

    elif isinstance(row, (list, tuple)):
        if len(row) != 2:
            raise ConfigError(
                f"{where}: a two-item row is [label, value], got {len(row)} items",
                hint="Write the full form instead:\n"
                "  - label: Tel.\n    value: '+39 ...'",
            )
        label, value, link, style = row[0], row[1], None, "normal"

    elif isinstance(row, dict):
        style = str(row.get("style", "normal")).lower()
        if style not in _ROW_STYLES:
            raise ConfigError(
                f"{where}.style: expected {_one_of(_ROW_STYLES)}, got {row['style']!r}"
            )
        label, value, link = row.get("label"), row.get("value"), row.get("link")

    else:
        raise ConfigError(
            f"{where}: expected a string, a [label, value] pair or a mapping, got {row!r}"
        )

    label, value, link = _as_text(label), _as_text(value), _as_text(link)
    # An e-mail address gets its link for free, however the row was written.
    if link is None and value and "@" in value and " " not in value:
        link = "mailto:" + value
    # Under PDF/UA-1 the band is a page artifact and an artifact may hold no
    # link, so the target is dropped and the address prints as the text it
    # always was. The underline goes with it — `letterhead.typ` draws one only
    # under something clickable, and an underline that is not a link is a lie
    # about the page. Nothing reflows; an underline occupies no width.
    if not links:
        link = None
    return {"label": label, "value": value, "link": link, "style": style}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _one_of(names: tuple[str, ...]) -> str:
    """``'rule', 'blank' or 'hide'`` — a short fixed vocabulary, in a sentence.

    Written from the tuple rather than beside it, so that a vocabulary gains an
    entry in one place: the tuple is also what the JSON schema is generated
    from, and a list spelled twice is a list that ends up spelled differently.
    """
    quoted = [repr(name) for name in names]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} or {quoted[-1]}"


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _colour_or(value: Any, field: str, fallback: str) -> str:
    """A colour the user may have left out, in which case the palette decides."""
    return fallback if value is None else units.to_colour(value, field)


def _weight(value: Any, field: str) -> Any:
    """A font weight, as a number from 100 to 900 or one of Typst's names."""
    if isinstance(value, bool):
        raise ConfigError(f"{field}: expected a font weight, got a boolean")
    if isinstance(value, int):
        if not 100 <= value <= 900:
            raise ConfigError(
                f"{field}: {value!r} is not a font weight",
                hint="Weights run from 100 (thin) to 900 (black); 400 is regular "
                "and 700 bold.",
            )
        return value
    if isinstance(value, str) and value.lower() in _FONT_WEIGHTS:
        return value.lower()
    raise ConfigError(
        f"{field}: {value!r} is not a font weight",
        hint=f"Use a number from 100 to 900, or one of: {', '.join(_FONT_WEIGHTS)}.",
    )


def _sides(value: Any, field: str) -> dict[str, bool]:
    """Which sides of a border are drawn, however the choice was written."""
    names = value if isinstance(value, (list, tuple)) else [value]
    drawn = {"left": False, "right": False, "top": False, "bottom": False}
    for name in names:
        key = str(name).lower()
        if key not in _BORDER_SIDES:
            raise ConfigError(
                f"{field}: {name!r} is not a side",
                hint=f"Use one of: {', '.join(_BORDER_SIDES)} — or a list of them.",
            )
        for side in _BORDER_SIDES[key]:
            drawn[side] = True
    return drawn


def _alignment(value: Any, field: str) -> str:
    text = str(value).lower()
    if text not in _ALIGNMENTS:
        raise ConfigError(
            f"{field}: expected one of {', '.join(_ALIGNMENTS)}, got {value!r}"
        )
    return text


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge ``override`` into ``base``, recursing into mappings.

    Lists replace rather than extend: a user who lists three footer columns
    means three, not three appended to the defaults.

    ``base`` starts as a copy of :data:`DEFAULT_CONFIG`, so at every step it is
    also the schema — which is what tells a section written in one language
    from a section with one setting in it. Merging ``{ top: 30mm }`` into
    ``page.margin`` has to keep ``x`` and ``bottom``; replacing it with a
    translation has to not.
    """
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
            and not i18n.is_translation(value, base[key])
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _reject_unknown_keys(
    merged: dict[str, Any],
    reference: dict[str, Any],
    path: Path,
    prefix: str = "",
) -> None:
    """Report keys the schema does not define, with the nearest known name.

    A silently ignored ``colours:`` is a bad afternoon; naming it is cheap.
    """
    for key, value in merged.items():
        where = f"{prefix}{key}"
        if key not in reference:
            suggestion = _closest(str(key), list(reference))
            hint = f"Did you mean '{prefix}{suggestion}'?" if suggestion else ""
            raise ConfigError(f"{path}: unknown setting '{where}'", hint=hint)
        # Only descend into sections with a fixed schema. `items`, `columns`
        # and the palette hold user data, and are validated by their resolvers;
        # a language map holds translations, and `de` is not a misspelling of
        # anything — `tagline: { en: ..., de: ... }` replaces the whole section.
        if (
            isinstance(value, dict)
            and isinstance(reference[key], dict)
            and reference[key]
            and key != "palette"
            and not i18n.is_translation(value, reference[key])
        ):
            _reject_unknown_keys(value, reference[key], path, prefix=f"{where}.")


def _closest(word: str, candidates: list[str]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(word, candidates, n=1, cutoff=0.7)
    return matches[0] if matches else None
