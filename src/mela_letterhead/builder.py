"""The build pipeline: Markdown in, PDF out.

Each document is built in its own directory under ``build_dir``, into which
everything it needs is copied first — the Typst module, the logo, the resolved
configuration. That costs a few kilobytes and buys two things: Typst compiles
with its root set to a directory containing nothing but this document, and the
directory can be read afterwards to see exactly what was handed to the
compiler. Nothing in it is an input; deleting it loses nothing.

The stages:

1. split the front matter from the body;
2. resolve the configuration for the document's language;
3. stage the build directory;
4. rewrite the Markdown for typesetting (:mod:`~mela_letterhead.markdown_prep`);
5. Pandoc, Markdown to Typst;
6. Typst, to PDF.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from . import config as config_module
from . import markdown_prep, toolchain
from .config import Config
from .document import Document, discover
from .errors import BuildError, ConfigError

ASSETS = Path(__file__).parent / "assets"

#: Image formats Typst can place. Anything else is refused here rather than
#: halfway through a compile.
LOGO_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}


class BuildResult(NamedTuple):
    """What came of building one document."""

    document: Document
    pdf: Path
    language: str
    pages: Optional[int] = None


def build_all(
    config: Config,
    sources: Optional[Sequence[Path]] = None,
    keep_build: bool = False,
    on_start: Optional[Any] = None,
) -> List[BuildResult]:
    """Build the given documents, or every document the configuration selects."""
    if sources:
        paths = [Path(source).resolve() for source in sources]
        for path in paths:
            if not path.is_file():
                raise BuildError(f"{path}: no such file")
    else:
        documents = config.data["documents"]
        paths = discover(
            config.source_dir,
            list(documents["include"]),
            list(documents["exclude"]),
        )
        if not paths:
            patterns = ", ".join(documents["include"])
            raise BuildError(
                f"no documents found in {config.source_dir} matching {patterns}",
                hint="Name a file explicitly, or adjust 'documents.include' in "
                f"{config_module.CONFIG_FILENAME}.",
            )

    results = []
    for path in paths:
        if on_start is not None:
            on_start(path)
        results.append(build_document(config, path, keep_build=keep_build))
    return results


def build_document(config: Config, source: Path, keep_build: bool = False) -> BuildResult:
    """Build one Markdown file into a PDF."""
    toolchain.require("pandoc")
    toolchain.require("typst")

    source = Path(source).resolve()
    document = Document.load(source, config.data["documents"]["date_format"])
    language = document.language or config.default_language
    resolved = config_module.resolve(config, document, language)

    if document.author:
        resolved["document"]["author"] = document.author

    workdir = _stage(config, document, resolved)

    body = markdown_prep.prepare(document.body, config.data["markdown"])
    prepared = workdir / "body.prep.md"
    prepared.write_text(body, encoding="utf-8")

    generated = workdir / "document.typ"
    _run_pandoc(config, prepared, generated)

    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = output_dir / f"{document.output_name}.pdf"
    _run_typst(config, workdir, generated, pdf)

    if not keep_build:
        shutil.rmtree(workdir, ignore_errors=True)

    return BuildResult(document=document, pdf=pdf, language=language)


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------


def _stage(config: Config, document: Document, resolved: Dict[str, Any]) -> Path:
    """Create the document's build directory and fill it."""
    workdir = config.build_dir / document.slug
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(ASSETS / "letterhead.typ", workdir / "letterhead.typ")

    logo = _stage_logo(config, workdir)
    resolved["brand"]["logo"] = logo

    (workdir / "document.json").write_text(
        json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return workdir


def _stage_logo(config: Config, workdir: Path) -> Optional[str]:
    """Copy the logo beside the Typst module, and return its name there."""
    configured = config.data["brand"].get("logo")
    if not configured:
        return None

    source = config.resolve_path(str(configured))
    if not source.is_file():
        raise ConfigError(
            f"brand.logo: {source} does not exist",
            hint="The path is read relative to "
            f"{config.path.name if config.path else config_module.CONFIG_FILENAME}. "
            "Remove the setting to set the brand name as a wordmark instead.",
        )

    suffix = source.suffix.lower()
    if suffix not in LOGO_SUFFIXES:
        formats = ", ".join(sorted(LOGO_SUFFIXES))
        raise ConfigError(
            f"brand.logo: Typst cannot place a {suffix or 'file with no extension'}",
            hint=f"Use one of: {formats}.",
        )

    name = "logo" + suffix
    shutil.copy2(source, workdir / name)
    return name


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


def _run_typst(config: Config, workdir: Path, source: Path, target: Path) -> None:
    command = ["typst", "compile", "--root", str(workdir)]
    for path in font_paths(config):
        command += ["--font-path", str(path)]
    command += [str(source), str(target)]
    toolchain.run(command)


def font_paths(config: Config) -> List[Path]:
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
