"""The ``mela-letterhead`` command."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from . import config as config_module
from . import builder, i18n, toolchain
from .config import Config
from .document import Document, discover
from .errors import LetterheadError

SCAFFOLD = Path(__file__).parent / "assets" / "scaffold"

#: The drawings the example document prints, copied beside the logo.
SCAFFOLD_PLATES = (
    "plate-collection-point.svg",
    "plate-condition.svg",
    "plate-roof-plan.svg",
)

_USE_COLOUR = sys.stdout.isatty()


def _paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text


def _bold(text: str) -> str:
    return _paint(text, "1")


def _dim(text: str) -> str:
    return _paint(text, "2")


def _green(text: str) -> str:
    return _paint(text, "32")


def _red(text: str) -> str:
    return _paint(text, "31")


def _yellow(text: str) -> str:
    return _paint(text, "33")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def command_init(args: argparse.Namespace) -> int:
    """Write a working letterhead into an empty directory."""
    target = Path(args.directory).resolve()
    target.mkdir(parents=True, exist_ok=True)

    files = [
        (SCAFFOLD / "letterhead.yaml", target / config_module.CONFIG_FILENAME),
        (SCAFFOLD / "logo.svg", target / "assets" / "logo.svg"),
        (SCAFFOLD / "example-letter.md", target / "example-letter.md"),
        # The plates the example document prints. Nothing else needs them.
        *[
            (SCAFFOLD / name, target / "assets" / name)
            for name in SCAFFOLD_PLATES
        ],
    ]

    existing = [destination for _, destination in files if destination.exists()]
    if existing and not args.force:
        print(_red("Nothing written: these files already exist."))
        for path in existing:
            print(f"  {_relative(path)}")
        print("\nRun again with --force to overwrite them.")
        return 1

    for origin, destination in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination)
        print(f"  {_green('created')}  {_relative(destination)}")

    print()
    print(f"A letterhead is ready in {_where(target)}.")
    print()
    print("Next:")
    print(
        f"  1. Put your own logo at {_bold('assets/logo.svg')} (PNG and JPEG work "
        f"too) — or delete {_bold('brand.logo')} and have your name set in type "
        "instead. Both are finished letterheads."
    )
    print(
        f"  2. Edit {_bold(config_module.CONFIG_FILENAME)} — the brand name, the "
        "colours, and the footer with your real details."
    )
    print(f"  3. Run {_bold('mela-letterhead build')} to print example-letter.pdf.")
    return 0


def command_build(args: argparse.Namespace) -> int:
    config = _load_config(args)
    sources = [Path(path) for path in args.documents] if args.documents else None

    results = builder.build_all(
        config,
        sources=sources,
        keep_build=args.keep_build,
        on_start=lambda path: print(f"  {_dim('building')}  {_relative(path)}"),
    )

    print()
    for result in results:
        size = _human_size(result.pdf)
        print(
            f"  {_green('✓')}  {_relative(result.pdf)}  "
            f"{_dim(f'[{result.language}, {size}]')}"
        )

    count = len(results)
    print()
    print(
        f"{count} document{'' if count == 1 else 's'} written to "
        f"{_where(config.output_dir)}."
    )
    if args.keep_build:
        print(_dim(f"Intermediates kept in {_relative(config.build_dir)}."))
    return 0


def command_check(args: argparse.Namespace) -> int:
    """Report on everything a build depends on, without building anything."""
    problems = 0

    print(_bold("Toolchain"))
    for name in ("pandoc", "typst"):
        tool = toolchain.find(name)
        if tool.available:
            developed = toolchain.DEVELOPED_WITH[name]
            note = _dim(f"(developed against {developed})")
            print(f"  {_green('✓')}  {name} {tool.version or '?'}  {note}")
        else:
            problems += 1
            print(f"  {_red('✗')}  {name} not found on PATH")

    print()
    try:
        config = _load_config(args)
    except LetterheadError as error:
        _report(error)
        return 1

    print(_bold("Configuration"))
    print(f"  {_green('✓')}  {_relative(config.path)} reads cleanly")
    brand = config.data["brand"].get("name") or _dim("(no brand name set)")
    print(f"     brand          {brand}")
    print(f"     language       {config.default_language}")

    # Both paths may be written as a language map, so they are resolved the way
    # a build would resolve them, in the project's own default language.
    chain = i18n.fallback_chain(config.default_language)
    logo = i18n.localise(config.data["brand"].get("logo"), chain)
    if logo:
        path = config.resolve_path(str(logo))
        if path.is_file():
            print(f"     logo           {_relative(path)}")
        else:
            problems += 1
            print(f"  {_red('✗')}  logo not found: {_relative(path)}")
    else:
        print(f"     logo           {_dim('none — the brand name is set as a wordmark')}")

    background = i18n.localise(config.data["page"]["background"].get("image"), chain)
    if background:
        path = config.resolve_path(str(background))
        if path.is_file():
            print(f"     background     {_relative(path)}")
        else:
            problems += 1
            print(f"  {_red('✗')}  background not found: {_relative(path)}")

    languages = i18n.available_locales(config.locales_dir)
    print(f"     locale packs   {', '.join(languages)}")

    # Reading cleanly is only half of it. Every colour, weight, length, footer
    # row and header field is settled in `resolve`, which `check` did not call
    # until now — so a letterhead could pass here and fail on the next command.
    # Resolved against a document with nothing in it, which is what leaves only
    # the letterhead's own mistakes.
    settings_resolve = True
    probe = Document(config.path or Path(config_module.CONFIG_FILENAME), {}, "")
    try:
        config_module.resolve(config, probe, config.default_language)
    except LetterheadError as error:
        settings_resolve = False
        problems += 1
        _problem(error.message, error.hint)
    else:
        print(f"  {_green('✓')}  every setting resolves")

    print()
    print(_bold("Fonts"))
    if toolchain.find("typst").available:
        font_paths = builder.font_paths(config)
        available = toolchain.typst_fonts(font_paths)
        stacks = config_module.resolve_fonts(config.data["fonts"])
        missing = toolchain.missing_fonts(list(stacks.values()), available)
        for role, stack in stacks.items():
            installed = next(
                (name for name in stack if name.casefold() in {f.casefold() for f in available}),
                None,
            )
            if installed:
                extra = _dim(f"(of {len(stack)} in the stack)") if len(stack) > 1 else ""
                print(f"  {_green('✓')}  {role:<8} {installed} {extra}")
            else:
                print(f"  {_yellow('!')}  {role:<8} none of {', '.join(stack)} is installed")
        if missing:
            problems += 1
            print()
            print(
                _yellow(
                    "  Typst substitutes a missing font silently, so the page will\n"
                    "  compile and come out looking different. Install the fonts, or\n"
                    "  point 'fonts.paths' at a directory holding them."
                )
            )
    else:
        print(_dim("  skipped — typst is not installed"))

    print()
    print(_bold("Documents"))
    documents = config.data["documents"]
    try:
        paths = discover(
            config.source_dir,
            list(documents["include"]),
            list(documents["exclude"]),
        )
    except LetterheadError as error:
        problems += 1
        paths = []
        print(f"  {_red('✗')}  {error.message}")

    if not paths:
        print(_dim("  none found"))
    for path in paths:
        try:
            document = Document.load(path, documents["date_format"])
        except LetterheadError as error:
            problems += 1
            _problem(f"{_relative(path)}: {error.message}", error.hint)
            continue

        language = document.language or config.default_language
        # In the document's own language, which is the one it will be built in:
        # a label or a colour written per language is only wrong in some of
        # them. Skipped when the letterhead itself did not resolve, so that one
        # bad colour is reported once rather than once per document.
        if settings_resolve:
            try:
                config_module.resolve(config, document, language)
            except LetterheadError as error:
                problems += 1
                _problem(f"{_relative(path)}: {error.message}", error.hint)
                continue

        print(
            f"  {_green('✓')}  {_relative(path)}  "
            f"{_dim(f'[{language}] → {document.output_name}.pdf')}"
        )

    print()
    if problems:
        print(_red(f"{problems} problem{'' if problems == 1 else 's'} found."))
        return 1
    print(_green("Everything checks out."))
    return 0


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------


def _load_config(args: argparse.Namespace) -> Config:
    path = Path(args.config) if getattr(args, "config", None) else None
    return config_module.load(path)


def _where(directory: Path) -> str:
    """Name a directory in a sentence. "." does not read as a place."""
    if Path(directory).resolve() == Path.cwd().resolve():
        return "this directory"
    return _bold(_relative(directory))


def _relative(path: Optional[Path]) -> str:
    """Show a path relative to the working directory when that is shorter."""
    if path is None:
        return "?"
    path = Path(path)
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return str(path)
    return str(relative) if len(str(relative)) < len(str(path)) else str(path)


def _human_size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "?"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} kB"
    return f"{size / (1024 * 1024):.1f} MB"


def _problem(message: str, hint: str = "") -> None:
    """Report a failure inside a `check` section, hint and all.

    The hint is where the useful half usually lives — which colours are
    colours, how a footer row is written — so it is printed here rather than
    kept for the one error that stops the command.
    """
    print(f"  {_red('✗')}  {message}")
    for line in hint.splitlines():
        print(f"     {_dim(line)}")


def _report(error: LetterheadError) -> None:
    print(f"{_red('Error')}: {error.message}", file=sys.stderr)
    if error.hint:
        print(file=sys.stderr)
        for line in error.hint.splitlines():
            print(f"  {line}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mela-letterhead",
        description="Turn Markdown into branded PDF documents, in any language.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mela-letterhead init .            scaffold a letterhead here\n"
            "  mela-letterhead build             build every document\n"
            "  mela-letterhead build offer.md    build one\n"
            "  mela-letterhead check             diagnose without building\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"mela-letterhead {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    initialiser = subparsers.add_parser(
        "init",
        help="write a working letterhead into a directory",
        description="Write a working letterhead — configuration, logo and an "
        "example document — into a directory.",
    )
    initialiser.add_argument(
        "directory", nargs="?", default=".", help="where to write it (default: here)"
    )
    initialiser.add_argument(
        "--force", action="store_true", help="overwrite files that already exist"
    )
    initialiser.set_defaults(handler=command_init)

    build = subparsers.add_parser(
        "build",
        help="build documents into PDFs",
        description="Build the named Markdown documents, or every document the "
        "configuration selects.",
    )
    build.add_argument("documents", nargs="*", help="Markdown files (default: all of them)")
    build.add_argument("-c", "--config", help=f"path to {config_module.CONFIG_FILENAME}")
    build.add_argument(
        "--keep-build",
        action="store_true",
        help="keep the intermediate Typst and Markdown files for inspection",
    )
    build.set_defaults(handler=command_build)

    check = subparsers.add_parser(
        "check",
        help="report on the toolchain, configuration, fonts and documents",
        description="Report on everything a build depends on, without building "
        "anything.",
    )
    check.add_argument("-c", "--config", help=f"path to {config_module.CONFIG_FILENAME}")
    check.set_defaults(handler=command_check)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "handler", None):
        parser.print_help()
        return 0

    try:
        return args.handler(args)
    except LetterheadError as error:
        _report(error)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
