"""The ``mela-letterhead`` command."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from . import __version__, builder, i18n, toolchain
from . import config as config_module
from .config import Config
from .document import Document
from .errors import LetterheadError

SCAFFOLD = Path(__file__).parent / "assets" / "scaffold"

#: The drawings the example document prints, copied beside the logo.
SCAFFOLD_PLATES = (
    "plate-collection-point.svg",
    "plate-condition.svg",
    "plate-roof-plan.svg",
)

#: The JSON Schema, as it ships inside the package.
SCHEMA_SOURCE = Path(__file__).parent / "assets" / "letterhead.schema.json"

#: And what it is called once it has been copied into a project. The scaffold's
#: first line names it by this, as a path relative to the letterhead, so the
#: two have to agree and a project stays movable: no URL to fetch, no absolute
#: path to go stale when the directory is renamed or handed to somebody else.
SCHEMA_FILENAME = "letterhead.schema.json"

#: How often `build --watch` looks. A build is around two tenths of a second,
#: so the poll is the whole of the latency between saving and seeing; a quarter
#: of a second costs a few dozen `stat` calls and nothing else.
WATCH_INTERVAL = 0.25

#: How long to wait after a change before building. An editor commonly writes a
#: temporary file and renames it over the original, which is two events a fifth
#: of a second apart; without this pause that is two builds.
WATCH_SETTLE = 0.15


def _use_colour() -> bool:
    """Whether to paint this line.

    Asked per line rather than once at import, so that a caller who redirects
    `sys.stdout` — a test, an editor plug-in, anything embedding the command —
    gets the answer for the stream actually being written to.

    Both conventions are read by presence, not by value: `NO_COLOR=0` is still
    somebody asking for no colour, and the empty string is how a shell says the
    variable is not set.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _use_colour() else text


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


def _fits(text: str) -> bool:
    """Whether the stream being written to can carry these characters.

    Windows hands a redirected command the ANSI code page rather than UTF-8,
    and there is no tick in it: a `check` on Windows CI ended in a
    `UnicodeEncodeError` on its first line of output, halfway through its own
    report. Asked per line, for the same reason `_use_colour` is.
    """
    encoding = getattr(sys.stdout, "encoding", None)
    if not encoding:
        return False
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _mark(preferred: str, plain: str) -> str:
    """One of two spellings of the same mark, whichever the stream can print.

    The tick and the cross keep their width between the two, so the columns
    after them line up on a code page as they do in UTF-8.
    """
    return preferred if _fits(preferred) else plain


def _tick() -> str:
    return _green(_mark("✓", "+"))


def _cross() -> str:
    return _red(_mark("✗", "x"))


def _harden_output() -> None:
    """Let a character the stream cannot print degrade rather than end the run.

    The marks above are chosen to fit, but a brand name, a path or a font
    family is whatever the user has, and on Windows the stream is a code page
    holding a couple of hundred characters. One outside it should cost a
    question mark, not a traceback over a half-written report.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # a stream something else has substituted
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):  # detached, or closed under us
            pass


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def command_init(args: argparse.Namespace) -> int:
    """Write a working letterhead into an empty directory."""
    target = Path(args.directory).resolve()
    target.mkdir(parents=True, exist_ok=True)

    files = [
        (SCAFFOLD / "letterhead.yaml", target / config_module.CONFIG_FILENAME),
        # What the letterhead's first line points at, which is why it is written
        # here rather than fetched: an editor reads it off the disk, offline,
        # and it is the schema belonging to the version that wrote the file.
        (SCHEMA_SOURCE, target / SCHEMA_FILENAME),
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


def _schema_is_current(path: Path) -> bool:
    """Whether a project's copy of the schema is this version's."""
    try:
        return path.read_bytes() == SCHEMA_SOURCE.read_bytes()
    except OSError:
        return False


def _points_at_schema(path: Path) -> bool:
    """Whether a letterhead already tells an editor where its schema is.

    Any modeline counts, not only one naming our file: somebody who has pointed
    their editor somewhere on purpose does not need advice about it.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True
    return any("yaml-language-server" in line for line in text.splitlines())


def command_schema(args: argparse.Namespace) -> int:
    """Write this version's JSON Schema into a project, for the editor to read.

    `init` already writes it, so this is for the two cases `init` cannot serve:
    a project made before the schema existed, and one whose copy is a release
    behind after an upgrade. It overwrites without asking because the file is
    generated, nobody edits it, and refusing to would make the ordinary case
    two commands.
    """
    target = Path(args.directory).resolve()
    target.mkdir(parents=True, exist_ok=True)
    destination = target / SCHEMA_FILENAME

    existed = destination.is_file()
    was_current = existed and _schema_is_current(destination)
    shutil.copy2(SCHEMA_SOURCE, destination)

    if not existed:
        print(f"  {_green('created')}  {_relative(destination)}")
    elif was_current:
        print(f"  {_tick()}  {_relative(destination)} was already this version's")
    else:
        print(f"  {_green('updated')}  {_relative(destination)}")

    config_path = target / config_module.CONFIG_FILENAME
    if config_path.is_file() and not _points_at_schema(config_path):
        print()
        print(f"{_relative(config_path)} does not point at it yet. Add this as its first line:")
        print()
        print(f"  {_bold(f'# yaml-language-server: $schema={SCHEMA_FILENAME}')}")
    return 0


def command_build(args: argparse.Namespace) -> int:
    config = _load_config(args)
    sources = [Path(path) for path in args.documents] if args.documents else None

    profile = getattr(args, "profile", None)

    if getattr(args, "watch", False):
        return _watch(config, sources, args.keep_build, profile)

    _build_once(config, sources, args.keep_build, profile)
    return 0


def _build_once(
    config: Config,
    sources: list[Path] | None,
    keep_build: bool,
    profile: str | None = None,
) -> list[builder.BuildResult]:
    """Build everything once and report on it.

    Returns the results rather than a status, because the one caller that has
    anything to do with them is `--watch`, which builds again from what they
    say the last build read.
    """
    results = builder.build_all(
        config,
        sources=sources,
        keep_build=keep_build,
        on_start=lambda path: print(f"  {_dim('building')}  {_relative(path)}"),
        profile=profile,
    )

    print()
    for result in results:
        size = _human_size(result.pdf)
        print(
            f"  {_tick()}  {_relative(result.pdf)}  "
            f"{_dim(f'[{result.language}, {size}]')}"
        )

    count = len(results)
    print()
    print(
        f"{count} document{'' if count == 1 else 's'} written to "
        f"{_where(config.output_dir)}."
    )
    if keep_build:
        print(_dim(f"Intermediates kept in {_relative(config.build_dir)}."))
    return results


# ---------------------------------------------------------------------------
# watching
# ---------------------------------------------------------------------------


def _watch(
    config: Config,
    sources: list[Path] | None,
    keep_build: bool,
    profile: str | None = None,
) -> int:
    """Build, and build again every time one of the files it read changes.

    A failed build does not end the session, which is the whole value of
    watching: the error is reported, the file that caused it stays watched, and
    saving it again is what makes the error go away. That is why the build is
    caught here rather than by `main`.
    """
    results: list[builder.BuildResult] = []
    build = True
    first = True

    try:
        while True:
            if build:
                try:
                    results = _build_once(config, sources, keep_build, profile)
                except LetterheadError as error:
                    _report(error)
                if first:
                    print()
                    print(_dim("Watching for changes. Ctrl-C to stop."))
                    first = False

            before = _watch_signature(_watched(config, sources, results))
            changed = _wait_for_change(config, sources, results, before)

            # A rule and a clock at the head of each pass, so that six builds
            # in a terminal read as six builds rather than as one long report.
            print()
            print(_watch_rule())

            # Editing the letterhead is the first thing anybody tries. A file
            # that does not read is reported and the old configuration kept, so
            # that half-typed YAML costs an error rather than the session; there
            # is nothing honest to build from it until it reads again.
            build = True
            if config.path is not None and config.path in changed:
                try:
                    config = config_module.load(config.path)
                except LetterheadError as error:
                    _report(error)
                    build = False
    except KeyboardInterrupt:
        # A watch stopped on purpose is not a failure. `main` still returns 130
        # for an interrupt during a one-shot build, which is one.
        print()
        print("Stopped watching.")
        return 0


def _watch_rule(width: int = 52) -> str:
    """The dim line between one pass and the next, with the time on it."""
    stamp = time.strftime("%H:%M:%S")
    dash = _mark("─", "-")
    return _dim(f"{dash * 3} {stamp} {dash * max(1, width - len(stamp) - 5)}")


def _watched(
    config: Config,
    sources: list[Path] | None,
    results: Sequence[builder.BuildResult],
) -> list[Path]:
    """Every file a rebuild would read, as far as it can be known.

    Three groups. The letterhead — the configuration, its locale packs, and the
    two pictures the configuration names, resolved the way a build resolves
    them because either may be written once per language. The documents —
    whichever were named, or whatever `builder.discover_documents` finds now,
    which is re-asked every pass so that a newly written document is picked up:
    it arrives in the next signature as a path that was not in the last one, and
    `_changed` compares the two key sets rather than only the values they share.
    Asked through the builder rather than of `discover` directly, so that a
    watch watches exactly what a build would read, and nothing the build itself
    wrote. Not the
    directory's own modification time, which POSIX moves when an entry is added
    and Windows does not — the source directory is watched because creating it
    is how a missing one gets fixed. And the pictures, which only a build that
    has already happened can name.
    """
    paths: list[Path] = []
    if config.path is not None:
        paths.append(config.path)
    if config.locales_dir.is_dir():
        paths.extend(sorted(config.locales_dir.glob("*.yaml")))
    paths.extend(_configured_pictures(config))

    if sources:
        paths.extend(Path(source).resolve() for source in sources)
    else:
        paths.append(config.source_dir)
        try:
            paths.extend(builder.discover_documents(config))
        except LetterheadError:
            # Reported by the build; the directory is still worth watching,
            # because creating it is how the user fixes this.
            pass

    for result in results:
        paths.extend(result.inputs)
    return paths


def _watch_signature(paths: Iterable[Path]) -> dict[Path, tuple[int, int]]:
    """What each path looks like now: its modification time and its size.

    Not the modification time alone. Some filesystems carry it to the second,
    and saving twice inside one second is the commonest edit there is; the size
    catches what the clock cannot. A path that is not there is left out
    entirely, so that deleting a file is a change and so is creating one.
    """
    signature: dict[Path, tuple[int, int]] = {}
    for path in paths:
        try:
            info = Path(path).stat()
        except OSError:
            continue
        signature[Path(path)] = (info.st_mtime_ns, info.st_size)
    return signature


def _changed(
    before: dict[Path, tuple[int, int]], after: dict[Path, tuple[int, int]]
) -> set[Path]:
    """The paths that differ between two signatures, either way round."""
    return {
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    }


def _wait_for_change(
    config: Config,
    sources: list[Path] | None,
    results: Sequence[builder.BuildResult],
    before: dict[Path, tuple[int, int]],
) -> set[Path]:
    """Poll until something moves, and return what did.

    The watch set is rebuilt on every pass rather than once, so that a document
    created while this is running is watched from the moment it exists.
    """
    while True:
        time.sleep(WATCH_INTERVAL)
        changed = _changed(before, _watch_signature(_watched(config, sources, results)))
        if not changed:
            continue
        # Let a write-then-rename finish before reading anything.
        time.sleep(WATCH_SETTLE)
        settled = _changed(before, _watch_signature(_watched(config, sources, results)))
        return settled or changed


def command_check(args: argparse.Namespace) -> int:
    """Report on everything a build depends on, without building anything."""
    problems = 0

    print(_bold("Toolchain"))
    for name in ("pandoc", "typst"):
        tool = toolchain.find(name)
        if not tool.available:
            problems += 1
            print(f"  {_cross()}  {name} not found on PATH")
        elif toolchain.too_old(tool):
            problems += 1
            minimum = toolchain.MINIMUM[name]
            print(
                f"  {_cross()}  {name} {tool.version}  "
                f"{_dim(f'(too old — this needs {minimum} or newer)')}"
            )
        else:
            developed = toolchain.DEVELOPED_WITH[name]
            note = _dim(f"(developed against {developed})")
            print(f"  {_tick()}  {name} {tool.version or '?'}  {note}")

    print()
    try:
        config = _load_config(args)
    except LetterheadError as error:
        _report(error)
        return 1

    profile = getattr(args, "profile", None)

    print(_bold("Configuration"))
    print(f"  {_tick()}  {_relative(config.path)} reads cleanly")
    brand = config.data["brand"].get("name") or _dim("(no brand name set)")
    print(f"     brand          {brand}")
    print(f"     language       {config.default_language}")
    if config.profiles:
        print(f"     profiles       {', '.join(sorted(config.profiles))}")
    if profile:
        # The flag applies to the whole run; a profile named in a document's
        # own front matter is reported against that document instead, where it
        # belongs.
        print(f"     profile        {profile}  {_dim('(from --profile)')}")

    # Both paths may be written as a language map, so they are resolved the way
    # a build would resolve them, in the project's own default language.
    logo = _configured_logo(config)
    if logo is not None:
        if logo.is_file():
            print(f"     logo           {_relative(logo)}")
        else:
            problems += 1
            print(f"  {_cross()}  logo not found: {_relative(logo)}")
    else:
        print(f"     logo           {_dim('none — the brand name is set as a wordmark')}")

    background = _configured_background(config)
    if background is not None:
        if background.is_file():
            print(f"     background     {_relative(background)}")
        else:
            problems += 1
            print(f"  {_cross()}  background not found: {_relative(background)}")

    languages = i18n.available_locales(config.locales_dir)
    print(f"     locale packs   {', '.join(languages)}")

    # The editor's copy of the schema, which is nobody's input: it changes
    # nothing about the page, so a stale one is said out loud and still leaves
    # `check` green. Worth saying at all because the failure it causes looks
    # like the tool's — a setting this version accepts, underlined in red by a
    # schema a release behind. A project without the file has not asked for
    # one, and is left alone.
    project_schema = config.directory / SCHEMA_FILENAME
    if project_schema.is_file() and not _schema_is_current(project_schema):
        print(f"  {_yellow('!')}  {SCHEMA_FILENAME} was written by another version")
        print(_dim("     Your editor is checking this letterhead against it."))
        print(_dim("     Run: mela-letterhead schema"))

    # Reading cleanly is only half of it. Every colour, weight, length, footer
    # row and header field is settled in `resolve`, which `check` did not call
    # until now — so a letterhead could pass here and fail on the next command.
    # Resolved against a document with nothing in it, which is what leaves only
    # the letterhead's own mistakes.
    settings_resolve = True
    probe = Document(config.path or Path(config_module.CONFIG_FILENAME), {}, "")
    try:
        resolved = config_module.resolve(
            config, probe, config.default_language, profile
        )
    except LetterheadError as error:
        settings_resolve = False
        problems += 1
        _problem(error.message, error.hint)
    else:
        print(f"  {_tick()}  every setting resolves")

        # Conformance itself is a question for the compiler, and `check`
        # compiles nothing. What it can settle is the half that is about this
        # machine rather than about the document: whether the Pandoc installed
        # here carries a picture's description as far as the page.
        standards = resolved["pdf"]["standard"]
        if standards:
            print(f"     pdf standard   {', '.join(standards)}")
            try:
                builder.require_alt_text_support(standards)
            except LetterheadError as error:
                problems += 1
                _problem(error.message, error.hint)

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
                print(f"  {_tick()}  {role:<8} {installed} {extra}")
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
        paths = builder.discover_documents(config)
    except LetterheadError as error:
        problems += 1
        paths = []
        print(f"  {_cross()}  {error.message}")

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
        try:
            # In the document's own language, which is the one it will be built
            # in: a label or a colour written per language is only wrong in some
            # of them. Skipped when the letterhead itself did not resolve, so
            # that one bad colour is reported once rather than once per
            # document — but the note is not, because reading the document's own
            # block can fail on its own account.
            if settings_resolve:
                config_module.resolve(config, document, language, profile)
            note = _overrides_note(document, profile)
        except LetterheadError as error:
            problems += 1
            _problem(f"{_relative(path)}: {error.message}", error.hint)
            continue

        # Hoisted because the nested f-string below cannot carry a quoted
        # argument of its own.
        arrow = _mark("→", "->")
        print(
            f"  {_tick()}  {_relative(path)}  "
            f"{_dim(f'[{language}] {arrow} {document.output_name}.pdf')}{note}"
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


def _configured_picture(config: Config, written: object) -> Path | None:
    """The file a picture setting names, in the project's own language.

    The logo and the page background are the two pictures the configuration
    owns, and either may be written as a language map — a brand with a mark per
    market. So neither can be read straight out of `config.data`, where such a
    map stringifies into a path that does not exist.
    """
    localised = i18n.localise(written, i18n.fallback_chain(config.default_language))
    return config.resolve_path(str(localised)) if localised else None


def _configured_logo(config: Config) -> Path | None:
    return _configured_picture(config, config.data["brand"].get("logo"))


def _configured_background(config: Config) -> Path | None:
    return _configured_picture(config, config.data["page"]["background"].get("image"))


def _configured_pictures(config: Config) -> list[Path]:
    """Both of them, leaving out whichever is not set."""
    named = (_configured_logo(config), _configured_background(config))
    return [path for path in named if path is not None]


def _where(directory: Path) -> str:
    """Name a directory in a sentence. "." does not read as a place."""
    if Path(directory).resolve() == Path.cwd().resolve():
        return "this directory"
    return _bold(_relative(directory))


def _relative(path: Path | None) -> str:
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


def _overrides_note(document: Document, profile: str | None) -> str:
    """What this document changes about the letterhead, if anything.

    The failure this feature will actually have is an override silently not
    applied, so `check` says which documents carry one and how much of one.
    """
    parts = []
    # The flag is reported once, against the configuration; what belongs here
    # is the profile this document asked for itself.
    if not profile and document.profile:
        parts.append(f"profile {document.profile}")
    settings = config_module.count_settings(document.overrides)
    if settings:
        parts.append(f"+{settings} override{'' if settings == 1 else 's'}")
    return f"  {_dim('(' + ', '.join(parts) + ')')}" if parts else ""


def _problem(message: str, hint: str = "") -> None:
    """Report a failure inside a `check` section, hint and all.

    The hint is where the useful half usually lives — which colours are
    colours, how a footer row is written — so it is printed here rather than
    kept for the one error that stops the command.
    """
    print(f"  {_cross()}  {message}")
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
            "  mela-letterhead build --watch     build again on every save\n"
            "  mela-letterhead check             diagnose without building\n"
            "  mela-letterhead schema            refresh the editor's schema\n"
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
    build.add_argument(
        "--watch",
        action="store_true",
        help="stay open and build again whenever something changes",
    )
    build.add_argument(
        "--profile",
        help="apply a profile from 'profiles:' to every document in this run",
    )
    build.set_defaults(handler=command_build)

    check = subparsers.add_parser(
        "check",
        help="report on the toolchain, configuration, fonts and documents",
        description="Report on everything a build depends on, without building "
        "anything.",
    )
    check.add_argument("-c", "--config", help=f"path to {config_module.CONFIG_FILENAME}")
    check.add_argument(
        "--profile",
        help="check the letterhead as this profile leaves it",
    )
    check.set_defaults(handler=command_check)

    schema = subparsers.add_parser(
        "schema",
        help="write the JSON Schema beside a letterhead, for the editor",
        description="Write this version's JSON Schema into a directory, so an "
        "editor with yaml-language-server can complete and check "
        f"{config_module.CONFIG_FILENAME}. `init` writes it too; run this "
        "after upgrading, or in a project made before it existed.",
    )
    schema.add_argument(
        "directory", nargs="?", default=".", help="where to write it (default: here)"
    )
    schema.set_defaults(handler=command_schema)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _harden_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "handler", None):
        parser.print_help()
        return 0

    try:
        # Bound through `set_defaults`, so argparse knows it only as an object.
        status: int = args.handler(args)
        return status
    except LetterheadError as error:
        _report(error)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
