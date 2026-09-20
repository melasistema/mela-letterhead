"""The build pipeline: Markdown in, PDF out.

Each document is built in its own directory under ``build_dir``, into which
everything it needs is copied first — the Typst module, the logo, the page
background, the resolved configuration. That costs a few kilobytes and buys two
things: Typst compiles
with its root set to a directory containing nothing but this document, and the
directory can be read afterwards to see exactly what was handed to the
compiler. Nothing in it is an input; deleting it loses nothing.

The stages:

1. split the front matter from the body;
2. resolve the configuration for the document's language;
3. stage the build directory;
4. rewrite the Markdown for typesetting (:mod:`~mela_letterhead.markdown_prep`);
5. Pandoc, Markdown to Typst;
6. stage the pictures the generated Typst asks for;
7. Typst, to PDF.

Step 6 comes after Pandoc because Pandoc is what says which pictures the
document actually uses: it writes each one as an ``image("…")`` call, path for
path as the Markdown had it. Those paths mean nothing inside the build
directory — Typst compiles with its root set there and can read nothing above
it — so each file is copied in and the call rewritten to where it landed.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple

from . import config as config_module
from . import markdown_prep, toolchain
from .config import Config
from .document import Document, discover
from .errors import BuildError, ConfigError, ToolchainError

ASSETS = Path(__file__).parent / "assets"

#: Image formats Typst can place. Anything else is refused here rather than
#: halfway through a compile.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

#: Where a document's pictures are copied to inside its build directory.
IMAGE_DIR = "images"

#: An ``image("…")`` call in the Typst that Pandoc generated. Pandoc writes the
#: path exactly as the Markdown had it, escaping only quotes and backslashes.
_IMAGE_CALL_RE = re.compile(r'(image\(\s*")((?:[^"\\]|\\.)*)(")')

#: A reference to something that is not a file. Typst places files, and fetches
#: nothing. Written narrowly so that a Windows path is not read as a scheme.
_REMOTE_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|data:)", re.IGNORECASE)

#: Characters kept in a staged picture's name. Everything else becomes a dash,
#: so that a name with a space or an accent in it cannot surprise the compiler.
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

#: Said whenever the build directory turns out not to be writable. It names the
#: setting rather than the directory, because the setting is the half the user
#: chose, and it says the directory is disposable because that is what makes
#: moving it the obvious fix rather than a worrying one.
_BUILD_DIR_HINT = (
    "Every document is staged into a directory of its own under 'build_dir' "
    "before it is compiled. Point that setting somewhere you can write, or fix "
    "the permissions here. Nothing in it is an input, so moving it loses "
    "nothing."
)


@contextmanager
def _attributing(setting: str, where: Path | None = None, hint: str = "") -> Iterator[None]:
    """Report a filesystem failure against the setting that chose the place.

    Staging is the one part of the pipeline that writes, and it was the one
    part whose failures did not reach the user as failures: a ``build_dir`` on
    a read-only mount, or one the user does not own, came out as a
    ``PermissionError`` from inside ``shutil``, several frames up a traceback,
    naming a directory the user never typed. Everything else in this tool names
    the setting behind the trouble, and now this does too.

    Each block is kept narrow enough that the attribution is true. A copy has
    two ends and either can fail, so a picture's staging is attributed to the
    picture — the one name that is right whichever end it was.

    ``where`` is left out where naming it would only repeat the name already
    given, which is the case for a picture: the document wrote
    ``assets/plate.svg`` and the file is at ``…/assets/plate.svg``.
    """
    try:
        yield
    except OSError as exc:
        place = f"{where}: " if where is not None else ""
        raise BuildError(f"{setting}: {place}{exc.strerror or exc}", hint=hint) from exc


class BuildResult(NamedTuple):
    """What came of building one document.

    No page count: Typst reports one only to a second invocation — `typst
    query` against a `#metadata` label the module would have to emit — and
    nothing reads it yet. That is the route when something does.

    ``inputs`` is every file that fed this build, on the user's disk rather
    than in the build directory: the document, the logo, the page background,
    then each picture the body refers to. Which pictures those are is not
    knowable before Pandoc has run, so a watch can only learn them from a build
    that has already happened — which is what this carries.
    """

    document: Document
    pdf: Path
    language: str
    inputs: tuple[Path, ...] = ()


def discover_documents(config: Config) -> list[Path]:
    """Every document this configuration selects.

    Public because three commands have to agree about what that is: ``build``
    builds them, ``check`` reports on them, and ``--watch`` watches them. Any
    one of the three asking the question differently is a way for ``check`` to
    pass what ``build`` refuses, which is the failure this project has already
    had once.

    It is also the only place that knows the build directory holds no
    documents — see :func:`~mela_letterhead.document.discover` for why that
    cannot be a pattern in ``documents.exclude``.
    """
    documents = config.data["documents"]
    return discover(
        config.source_dir,
        list(documents["include"]),
        list(documents["exclude"]),
        skip=config.build_dir,
    )


def build_all(
    config: Config,
    sources: Sequence[Path] | None = None,
    keep_build: bool = False,
    on_start: Callable[[Path], None] | None = None,
    profile: str | None = None,
) -> list[BuildResult]:
    """Build the given documents, or every document the configuration selects."""
    if sources:
        paths = [Path(source).resolve() for source in sources]
        for path in paths:
            if not path.is_file():
                raise BuildError(f"{path}: no such file")
    else:
        paths = discover_documents(config)
        if not paths:
            patterns = ", ".join(config.data["documents"]["include"])
            raise BuildError(
                f"no documents found in {config.source_dir} matching {patterns}",
                hint="Name a file explicitly, or adjust 'documents.include' in "
                f"{config_module.CONFIG_FILENAME}.",
            )

    results = []
    for path in paths:
        if on_start is not None:
            on_start(path)
        results.append(
            build_document(config, path, keep_build=keep_build, profile=profile)
        )
    return results


def build_document(
    config: Config,
    source: Path,
    keep_build: bool = False,
    profile: str | None = None,
) -> BuildResult:
    """Build one Markdown file into a PDF."""
    toolchain.require("pandoc")
    toolchain.require("typst")

    source = Path(source).resolve()
    document = Document.load(source, config.data["documents"]["date_format"])
    language = document.language or config.default_language
    resolved = config_module.resolve(config, document, language, profile)

    if document.author:
        resolved["document"]["author"] = document.author

    require_alt_text_support(resolved["pdf"]["standard"])

    # Filled as the staging goes, in the order the files are read, so that
    # whatever wants to know what this build depended on gets the list without
    # a second pass over anything.
    inputs: list[Path] = [source]

    workdir = _stage(config, document, resolved, inputs)

    body = markdown_prep.prepare(document.body, config.data["markdown"])
    prepared = workdir / "body.prep.md"
    with _attributing("build_dir", config.build_dir, _BUILD_DIR_HINT):
        prepared.write_text(body, encoding="utf-8")

    generated = workdir / "document.typ"
    _run_pandoc(config, prepared, generated)
    _stage_images(source.parent, workdir, generated, inputs)

    output_dir = config.output_dir
    with _attributing(
        "documents.output",
        output_dir,
        hint="This is where the finished PDFs are written. Point "
        "'documents.output' somewhere you can write, or fix the permissions "
        "here.",
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
    pdf = output_dir / f"{document.output_name}.pdf"
    _run_typst(config, workdir, generated, pdf, resolved["pdf"]["standard"])

    if not keep_build:
        shutil.rmtree(workdir, ignore_errors=True)

    return BuildResult(
        document=document, pdf=pdf, language=language, inputs=tuple(inputs)
    )


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------


def _stage(
    config: Config,
    document: Document,
    resolved: dict[str, Any],
    inputs: list[Path] | None = None,
) -> Path:
    """Create the document's build directory and fill it."""
    workdir = config.build_dir / document.slug
    with _attributing("build_dir", config.build_dir, _BUILD_DIR_HINT):
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True, exist_ok=True)
        # Our own file, so a failure copying it is about the destination.
        shutil.copy2(ASSETS / "letterhead.typ", workdir / "letterhead.typ")

    # Both of these arrive as the path the user wrote and leave as the name
    # the file landed under here, which is all Typst ever sees of them.
    resolved["brand"]["logo"] = _stage_logo(
        config, workdir, resolved["brand"]["logo"], inputs
    )
    background = resolved["page"]["background"]
    background["image"] = _stage_background(
        config, workdir, background["image"], inputs
    )

    with _attributing("build_dir", config.build_dir, _BUILD_DIR_HINT):
        (workdir / "document.json").write_text(
            json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return workdir


def _stage_logo(
    config: Config,
    workdir: Path,
    configured: str | None,
    inputs: list[Path] | None = None,
) -> str | None:
    """The brand's mark, as the configuration names it."""
    return _stage_asset(
        config,
        workdir,
        configured,
        "brand.logo",
        "logo",
        missing="Remove the setting to set the brand name as a wordmark instead.",
        inputs=inputs,
    )


def _stage_background(
    config: Config,
    workdir: Path,
    configured: str | None,
    inputs: list[Path] | None = None,
) -> str | None:
    """The picture behind the page, as the configuration names it.

    The advice matters more here than for the logo, because the likeliest way
    to arrive at this setting is with a sheet that was drawn for a printer and
    exists as a PDF.
    """
    return _stage_asset(
        config,
        workdir,
        configured,
        "page.background.image",
        "background",
        unplaceable="A sheet drawn in a page-layout program has to be exported "
        "raster — PNG or JPEG, 300 dpi for print.",
        inputs=inputs,
    )


def _stage_asset(
    config: Config,
    workdir: Path,
    configured: str | None,
    setting: str,
    stem: str,
    missing: str = "",
    unplaceable: str = "",
    inputs: list[Path] | None = None,
) -> str | None:
    """Copy a picture the configuration names, and return its name here.

    The logo and the page background are both read relative to the
    configuration file rather than the document that is being printed: they
    belong to the letterhead, and nothing written on it refers to them. That
    is the whole difference between these two and :func:`_stage_images`.

    Both are refused by name when Typst could not place them, before a compile
    that would fail halfway through with something less helpful.

    ``inputs`` is appended to rather than returned alongside the name, because
    this has two callers and a richer return would ripple through both for the
    sake of one list.
    """
    if not configured:
        return None

    source = config.resolve_path(configured)
    if not source.is_file():
        where = config.path.name if config.path else config_module.CONFIG_FILENAME
        raise ConfigError(
            f"{setting}: {source} does not exist",
            hint=f"The path is read relative to {where}. {missing}".strip(),
        )

    suffix = source.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        formats = ", ".join(sorted(IMAGE_SUFFIXES))
        raise ConfigError(
            f"{setting}: Typst cannot place a {suffix or 'file with no extension'}",
            hint=f"Use one of: {formats}. {unplaceable}".strip(),
        )

    name = stem + suffix
    # Attributed to the setting, not to the build directory: this copy has the
    # user's file at one end and is as likely to fail there.
    with _attributing(setting, source):
        shutil.copy2(source, workdir / name)
    if inputs is not None:
        inputs.append(source)
    return name


def _stage_images(
    source_dir: Path,
    workdir: Path,
    generated: Path,
    inputs: list[Path] | None = None,
) -> list[str]:
    """Copy the pictures the generated Typst asks for, and repoint it at them.

    Paths are read relative to the document that names them, which is where a
    writer looking at the Markdown would expect them to be. Every file lands in
    one directory under its own name, so the build directory shows at a glance
    what the document is carrying; a name used twice gains a number.

    What is returned is the names the files landed under here. ``inputs``, by
    contrast, collects the paths they came from, which is the only form of any
    use to something watching the user's disk.
    """
    text = generated.read_text(encoding="utf-8")
    staged: dict[str, str] = {}
    taken: dict[Path, str] = {}

    def place(match: re.Match[str]) -> str:
        written = _unescape(match.group(2))
        if written not in staged:
            staged[written] = _stage_one_image(
                source_dir, workdir, written, taken, inputs
            )
        return match.group(1) + staged[written] + match.group(3)

    rewritten = _IMAGE_CALL_RE.sub(place, text)
    if staged:
        generated.write_text(rewritten, encoding="utf-8")
    # By staged name, not by the spellings that reached it: `plate.svg` and
    # `./plate.svg` are one picture, copied once.
    return sorted(set(staged.values()))


def _undescribed_pictures(generated: str) -> list[str]:
    """The pictures in the generated Typst that carry no description.

    Asked only once Typst has refused a document for want of alt text, and
    never to decide whether it should be refused. Typst says ``missing alt
    text`` without naming a picture, which in a document carrying a dozen of
    them is the start of a search rather than the end of one; this supplies the
    names. Leaving the judgement to Typst is also what keeps a picture
    described in some way this does not recognise — a ``figure`` given the
    description instead of the image inside it — from being refused over a
    reading of the file rather than a fact about it.

    The names are as they stand in the file, which by this point is after
    :func:`_stage_images` has run: the directory the picture was copied into,
    then the name it landed under. The caller drops the directory.
    """
    return sorted(
        {
            _unescape(match.group(2))
            for match in _IMAGE_CALL_RE.finditer(generated)
            if "alt:" not in _arguments_of(generated, match.end())
        }
    )


def _arguments_of(text: str, start: int) -> str:
    """The rest of a call whose opening bracket has already been passed.

    Scanned rather than matched, because the argument that is being looked for
    is a description written by a human: ``alt: "the tank (2000 l)"`` closes a
    bracket the call did not open, and a quotation mark would end the string a
    pattern was counting on.
    """
    depth = 1
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            index = _end_of_string(text, index + 1)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return text[start:index]
        index += 1
    return text[start:]


def _end_of_string(text: str, index: int) -> int:
    """The index just past the closing quotation mark of a Typst string."""
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == '"':
            return index + 1
        index += 1
    return index


def _stage_one_image(
    source_dir: Path,
    workdir: Path,
    written: str,
    taken: dict[Path, str],
    inputs: list[Path] | None = None,
) -> str:
    """Copy one picture into the build directory and return its name there."""
    if _REMOTE_RE.match(written):
        raise BuildError(
            f"{written}: Typst places files and fetches nothing",
            hint="Download the picture next to the document and refer to it by "
            "its file name.",
        )

    source = Path(written).expanduser()
    if not source.is_absolute():
        source = source_dir / source

    if not source.is_file():
        raise BuildError(
            f"{written}: no such picture",
            hint=f"The path is read relative to the document, in {source_dir}.",
        )

    source = source.resolve()
    if source in taken:
        return taken[source]

    suffix = source.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        formats = ", ".join(sorted(IMAGE_SUFFIXES))
        raise BuildError(
            f"{written}: Typst cannot place a {suffix or 'file with no extension'}",
            hint=f"Use one of: {formats}.",
        )

    used = {placed.rpartition("/")[2] for placed in taken.values()}
    name = _unique_name(_UNSAFE_RE.sub("-", source.name), used)
    destination = workdir / IMAGE_DIR / name
    # By the name the document wrote, for the same reason as in `_stage_asset`,
    # and spelled the way its neighbour above spells `no such picture`.
    with _attributing(written):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    placed = f"{IMAGE_DIR}/{name}"
    taken[source] = placed
    if inputs is not None:
        inputs.append(source)
    return placed


def _unique_name(name: str, used: set[str]) -> str:
    """Number a name that two different files would otherwise share."""
    if name not in used:
        return name
    stem, _, suffix = name.rpartition(".")
    stem, suffix = (stem, f".{suffix}") if stem else (name, "")
    index = 2
    while f"{stem}-{index}{suffix}" in used:
        index += 1
    return f"{stem}-{index}{suffix}"


def _unescape(path: str) -> str:
    """Undo the escaping Pandoc applies inside a Typst string literal."""
    return path.replace('\\"', '"').replace("\\\\", "\\")


def _run_pandoc(config: Config, source: Path, target: Path) -> None:
    markdown = config.data["markdown"]
    extra = markdown.get("extra_args") or []
    if not isinstance(extra, list) or not all(isinstance(arg, str) for arg in extra):
        raise ConfigError("markdown.extra_args: expected a list of strings")

    command = [
        "pandoc",
        str(source),
        "--from",
        str(markdown["format"]),
        "--to",
        "typst",
        "--template",
        str(ASSETS / "pandoc-typst.template"),
        "--output",
        str(target),
        *extra,
    ]
    toolchain.run(command)


def _run_typst(
    config: Config,
    workdir: Path,
    source: Path,
    target: Path,
    standards: Sequence[str] = (),
) -> None:
    command = ["typst", "compile", "--root", str(workdir)]
    for path in font_paths(config):
        command += ["--font-path", str(path)]
    if standards:
        command += ["--pdf-standard", ",".join(standards)]
    command += [str(source), str(target)]

    if not standards:
        toolchain.run(command)
        return

    # Typst is the authority on what a standard demands and on which of them
    # can be asked for together, and says both precisely. What it cannot say is
    # where the request came from — its message is about a command-line flag
    # nobody typed — so that much is added here, along with the names of the
    # pictures behind the one complaint it makes without naming anything.
    try:
        toolchain.run(command)
    except ToolchainError as exc:
        raise BuildError(
            exc.message,
            hint=_standard_hint(source, standards, exc.message),
        ) from exc


def _standard_hint(source: Path, standards: Sequence[str], message: str) -> str:
    asked = f"Asked for by 'pdf.standard: [{', '.join(standards)}]'."
    if "alt text" not in message:
        return asked
    undescribed = _undescribed_pictures(source.read_text(encoding="utf-8"))
    if not undescribed:
        return asked
    named = ", ".join(path.rpartition("/")[2] for path in undescribed)
    return (
        f"{asked} Without a description: {named}. Write one in the square "
        "brackets — ![a roof plan, with the plates numbered](plate.svg) — "
        "saying what the picture says rather than that there is a picture."
    )


def require_alt_text_support(standards: Sequence[str]) -> None:
    """Refuse an accessible standard to a Pandoc that drops the descriptions.

    Public because ``check`` asks it too: this is the one thing about a
    ``pdf.standard`` that can be settled without compiling anything, and it is
    also the one that would otherwise be reported as a document's fault. An old
    Pandoc does not fail — it writes the picture and leaves the description
    behind — so the build gets as far as Typst and is refused there for want of
    alt text the document plainly has.
    """
    wanted = sorted(set(standards) & config_module.PDF_STANDARDS_NEEDING_ALT_TEXT)
    if not wanted:
        return
    pandoc = toolchain.find("pandoc")
    if not pandoc.available or toolchain.carries_alt_text(pandoc):
        return
    raise ConfigError(
        f"pdf.standard: {', '.join(wanted)} needs every picture described, and "
        f"pandoc {pandoc.version} does not carry a description into the page",
        hint=f"Pandoc {toolchain.PANDOC_ALT_TEXT} is the first that does. Until "
        "then the descriptions are dropped on the way and the document is "
        "refused for missing what it has. Upgrade Pandoc, or ask for a "
        "conformance level that does not require it — 'a-2b' and 'a-3b' "
        "are the archival ones.",
    )


def font_paths(config: Config) -> list[Path]:
    paths = config.data["fonts"].get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        raise ConfigError("fonts.paths: expected a list of directories")

    resolved = []
    for entry in paths:
        path = config.resolve_path(str(entry))
        if not path.is_dir():
            raise ConfigError(f"fonts.paths: {path} is not a directory")
        resolved.append(path)
    return resolved
