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
from typing import Any, Dict, List, Optional

import yaml

from . import i18n, units
from .errors import ConfigError

CONFIG_FILENAME = "letterhead.yaml"

#: Alternative names accepted when looking for a project's configuration.
CONFIG_FILENAMES = (CONFIG_FILENAME, "letterhead.yml", ".letterhead.yaml")

#: The written shape, with every default filled in. A user's file is merged on
#: top of this, key by key, so a configuration may be as short as a brand name.
DEFAULT_CONFIG: Dict[str, Any] = {
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

#: What each name for a border's sides expands to.
_BORDER_SIDES: Dict[str, tuple] = {
    "all": ("left", "right", "top", "bottom"),
    "none": (),
    "left": ("left",),
    "right": ("right",),
    "top": ("top",),
    "bottom": ("bottom",),
    "x": ("left", "right"),
    "y": ("top", "bottom"),
}


class Config:
    """A loaded configuration, together with where it came from.

    ``directory`` is what every relative path in the file resolves against, so
    a configuration can be used from any working directory.
    """

    def __init__(self, data: Dict[str, Any], path: Optional[Path]) -> None:
        self.data = data
        self.path = path
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


def find_config(start: Optional[Path] = None) -> Optional[Path]:
    """Search ``start`` and its parents for a letterhead configuration."""
    directory = (start or Path.cwd()).resolve()
    for candidate_dir in [directory, *directory.parents]:
        for name in CONFIG_FILENAMES:
            candidate = candidate_dir / name
            if candidate.is_file():
                return candidate
    return None


def load(path: Optional[Path] = None, start: Optional[Path] = None) -> Config:
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
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: {exc.strerror or exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: the file must contain a mapping at the top level")

    version = raw.get("version", DEFAULT_CONFIG["version"])
    if isinstance(version, int) and version > DEFAULT_CONFIG["version"]:
        raise ConfigError(
            f"{path}: this file declares version {version}, but this release "
            f"understands up to version {DEFAULT_CONFIG['version']}",
            hint="Upgrade mela-letterhead, or lower the 'version' key.",
        )

    merged = _deep_merge(copy.deepcopy(DEFAULT_CONFIG), raw)
    _reject_unknown_keys(merged, DEFAULT_CONFIG, path)
    return Config(merged, path)


def resolve(config: Config, document: "Any", language: str) -> Dict[str, Any]:
    """Produce the resolved configuration for one document in one language.

    ``document`` is a :class:`~mela_letterhead.document.Document`; it supplies
    the values of the header fields and the document's own title.
    """
    chain = i18n.fallback_chain(language, config.default_language)
    strings = i18n.load_locale(chain, config.locales_dir)
    data = i18n.localise(copy.deepcopy(config.data), chain, DEFAULT_CONFIG)

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

    header = _resolve_header(data["header"], document, palette)
    running = _resolve_running(data["running"], strings, data["brand"], document)
    footer = _resolve_footer(data["footer"], palette)

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
        "fonts": fonts,
        "typography": _resolve_typography(data["typography"]),
        "images": _resolve_images(data["images"]),
        "header": header,
        "running": running,
        "footer": footer,
    }


# ---------------------------------------------------------------------------
# section resolvers
# ---------------------------------------------------------------------------


def resolve_fonts(fonts: Dict[str, Any]) -> Dict[str, Any]:
    default = DEFAULT_CONFIG["fonts"]
    serif = _font_stack(fonts.get("serif"), "fonts.serif", default["serif"])
    sans = _font_stack(fonts.get("sans"), "fonts.sans", default["sans"])
    return {
        "serif": serif,
        "sans": sans,
        "display": _font_stack(fonts.get("display"), "fonts.display", serif),
        "mono": _font_stack(fonts.get("mono"), "fonts.mono", default["mono"]),
    }


def _font_stack(value: Any, field: str, fallback: Optional[List[str]] = None) -> List[str]:
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
    wordmark: Dict[str, Any],
    fonts: Dict[str, Any],
    palette: Dict[str, str],
    mark_width: float,
    band_ink: str,
) -> Dict[str, Any]:
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
    fonts: Dict[str, Any],
    mark_width: float,
    band_muted: str,
) -> Dict[str, Any]:
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


def _resolve_border(border: Dict[str, Any], palette: Dict[str, str]) -> Dict[str, Any]:
    """The rule around the paper, and which of its four sides are drawn."""
    return {
        "width": units.to_points(border["width"], "page.border.width"),
        "color": _colour_or(border["color"], "page.border.color", palette["accent"]),
        "inset": units.to_points(border["inset"], "page.border.inset"),
        "sides": _sides(border["sides"], "page.border.sides"),
    }


def _resolve_background(background: Dict[str, Any]) -> Dict[str, Any]:
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


def _resolve_typography(typography: Dict[str, Any]) -> Dict[str, Any]:
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


def _resolve_images(images: Dict[str, Any]) -> Dict[str, Any]:
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
    header: Dict[str, Any], document: "Any", palette: Dict[str, str]
) -> Dict[str, Any]:
    fields = header["fields"]
    when_empty = str(fields.get("when_empty", "rule")).lower()
    if when_empty not in ("rule", "blank", "hide"):
        raise ConfigError(
            f"header.fields.when_empty: expected 'rule', 'blank' or 'hide', "
            f"got {fields['when_empty']!r}"
        )

    items: List[Dict[str, Any]] = []
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
    running: Dict[str, Any],
    strings: Dict[str, Any],
    brand: Dict[str, Any],
    document: "Any",
) -> Dict[str, Any]:
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


def _resolve_footer(footer: Dict[str, Any], palette: Dict[str, str]) -> Dict[str, Any]:
    pages = str(footer.get("pages", "last")).lower()
    if pages not in ("last", "all"):
        raise ConfigError(
            f"footer.pages: expected 'last' or 'all', got {footer['pages']!r}",
            hint="'last' prints the band on the final page only; 'all' on every page.",
        )

    columns = []
    for index, column in enumerate(footer.get("columns") or []):
        columns.append(_resolve_footer_column(column, f"footer.columns[{index}]"))

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


def _resolve_footer_column(column: Any, where: str) -> Dict[str, Any]:
    if not isinstance(column, dict):
        raise ConfigError(
            f"{where}: expected a mapping with 'title' and 'rows', got {column!r}"
        )
    title = column.get("title")
    if title is not None and not isinstance(title, str):
        title = str(title)

    rows = []
    for index, row in enumerate(column.get("rows") or []):
        rows.append(_resolve_footer_row(row, f"{where}.rows[{index}]"))
    return {"title": title, "rows": rows}


def _resolve_footer_row(row: Any, where: str) -> Dict[str, Any]:
    """Expand the three ways a footer row may be written.

    ``"Some line"``              a line with no label
    ``["Tel.", "+39 ..."]``      a label and a value
    ``{label:, value:, ...}``    the full form, with ``link`` and ``style``
    """
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
        if style not in ("normal", "highlight", "muted"):
            raise ConfigError(
                f"{where}.style: expected 'normal', 'highlight' or 'muted', "
                f"got {row['style']!r}"
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
    return {"label": label, "value": value, "link": link, "style": style}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _as_text(value: Any) -> Optional[str]:
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


def _sides(value: Any, field: str) -> Dict[str, bool]:
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


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
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
    merged: Dict[str, Any],
    reference: Dict[str, Any],
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


def _closest(word: str, candidates: List[str]) -> Optional[str]:
    import difflib

    matches = difflib.get_close_matches(word, candidates, n=1, cutoff=0.7)
    return matches[0] if matches else None
