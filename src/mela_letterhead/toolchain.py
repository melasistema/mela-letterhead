"""Locating and running Pandoc and Typst.

Both are external programs, and both fail in ways worth translating: a missing
binary should say how to install it, and a compiler error should reach the user
as the compiler wrote it, not wrapped in a Python traceback.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

from .errors import ToolchainError

#: Versions the tool was developed against. Older ones usually work; this is
#: what gets reported when something does not.
DEVELOPED_WITH = {"pandoc": "3.11", "typst": "0.15.1"}

#: The oldest release of each that this can be run on.
#:
#: Pandoc's floor is what CI tests on purpose: apt ships 3.1, whose Typst writer
#: spells two helpers differently, and `assets/pandoc-typst.template` polyfills
#: exactly those two. Below it nobody has looked.
#:
#: Typst's floor is the newest thing `assets/letterhead.typ` asks for, which is
#: the `std` module the divider polyfill tests against — 0.12. An older Typst
#: fails inside the module with a message about a name it has never heard of,
#: which is a long way from "this needs a newer Typst".
MINIMUM = {"pandoc": "3.1", "typst": "0.12"}

#: How long either program may run before it is taken to be wedged rather than
#: busy. Generous on purpose: the four-page scaffold compiles in a fifth of a
#: second, so two minutes is not a long document, it is a hang.
RUN_TIMEOUT = 120

_INSTALL_HINTS = {
    "pandoc": (
        "Install it with:\n"
        "  macOS    brew install pandoc\n"
        "  Debian   sudo apt install pandoc\n"
        "  Windows  winget install --id JohnMacFarlane.Pandoc\n"
        "or from https://pandoc.org/installing.html"
    ),
    "typst": (
        "Install it with:\n"
        "  macOS    brew install typst\n"
        "  Linux    cargo install --locked typst-cli\n"
        "  Windows  winget install --id Typst.Typst\n"
        "or from https://github.com/typst/typst/releases"
    ),
}


class Tool(NamedTuple):
    """An external program, found or not."""

    name: str
    path: Optional[str]
    version: Optional[str]

    @property
    def available(self) -> bool:
        return self.path is not None


def find(name: str) -> Tool:
    """Look ``name`` up on PATH and read its version."""
    path = shutil.which(name)
    if path is None:
        return Tool(name, None, None)
    return Tool(name, path, _read_version(path))


def require(name: str) -> Tool:
    """Like :func:`find`, but raise if the program is missing or too old."""
    tool = find(name)
    if not tool.available:
        raise ToolchainError(
            f"{name} is not installed, or not on your PATH",
            hint=_INSTALL_HINTS.get(name, ""),
        )
    if too_old(tool):
        raise ToolchainError(
            f"{name} {tool.version} is too old: this needs {name} "
            f"{MINIMUM[name]} or newer",
            hint=_INSTALL_HINTS.get(name, ""),
        )
    return tool


def too_old(tool: Tool) -> bool:
    """Whether ``tool`` is older than the release this can be run on.

    A version that could not be read is not called too old. It is a program
    that answered `--version` with something unexpected, and refusing to build
    over that would be worse than letting it try.
    """
    minimum = MINIMUM.get(tool.name)
    if minimum is None or tool.version is None:
        return False
    return _version_tuple(tool.version) < _version_tuple(minimum)


def run(command: Sequence[str], cwd: Optional[Path] = None) -> str:
    """Run ``command``, returning its standard output.

    A non-zero exit becomes a :class:`ToolchainError` carrying whatever the
    program said, because that message is almost always the useful one.
    """
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT,
        )
    # TimeoutExpired descends from SubprocessError, not OSError, so it has to be
    # caught on its own — and before the arm below, which would not see it.
    except subprocess.TimeoutExpired as exc:
        raise ToolchainError(
            f"{Path(command[0]).name} did not finish within {RUN_TIMEOUT} seconds",
            hint="Something is wedged rather than busy: the four-page example "
            "builds in a fifth of a second. Run the build again with "
            "--keep-build and try the command yourself in the build directory.",
        ) from exc
    except OSError as exc:
        raise ToolchainError(f"could not run {command[0]}: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ToolchainError(
            f"{Path(command[0]).name} exited with status {completed.returncode}"
            + (f"\n\n{detail}" if detail else "")
        )
    return completed.stdout


def typst_fonts(font_paths: Sequence[Path] = ()) -> List[str]:
    """Every font family Typst can see, including any extra font paths."""
    command = ["typst", "fonts"]
    for path in font_paths:
        command += ["--font-path", str(path)]
    try:
        output = run(command)
    except ToolchainError:
        return []
    return sorted({line.strip() for line in output.splitlines() if line.strip()})


def missing_fonts(wanted: Sequence[Sequence[str]], available: Sequence[str]) -> List[List[str]]:
    """Return the font stacks of which not one font is installed.

    A stack is fine as long as *some* entry resolves: that is what a fallback
    list is for. Only a stack that resolves to nothing changes the page, and
    Typst substitutes silently when it does.
    """
    installed = {name.casefold() for name in available}
    return [
        list(stack)
        for stack in wanted
        if stack and not any(name.casefold() in installed for name in stack)
    ]


def _read_version(path: str) -> Optional[str]:
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", completed.stdout or "")
    return match.group(1) if match else None


def _version_tuple(version: str) -> Tuple[int, ...]:
    """A dotted version as numbers, so that 0.9 sorts below 0.12."""
    return tuple(int(part) for part in re.findall(r"\d+", version))
