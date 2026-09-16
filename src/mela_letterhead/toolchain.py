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
from typing import List, NamedTuple, Optional, Sequence

from .errors import ToolchainError

#: Versions the tool was developed against. Older ones usually work; this is
#: what gets reported when something does not.
DEVELOPED_WITH = {"pandoc": "3.11", "typst": "0.15.1"}

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
    """Like :func:`find`, but raise if the program is missing."""
    tool = find(name)
    if not tool.available:
        raise ToolchainError(
            f"{name} is not installed, or not on your PATH",
            hint=_INSTALL_HINTS.get(name, ""),
        )
    return tool


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
        )
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
