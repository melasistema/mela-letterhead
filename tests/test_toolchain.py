"""Finding Pandoc and Typst, and refusing them for the right reasons.

Nothing here runs either program. What is being tested is the translation
layer: a missing binary, one too old to compile what this module writes, and
one that has stopped answering — each has to reach the user as a sentence
naming the program, rather than as a traceback or a hang.
"""

import subprocess

import pytest

from mela_letterhead import toolchain
from mela_letterhead.errors import ToolchainError


class TestVersionFloor:
    @pytest.mark.parametrize(
        "version, expected",
        [
            ("0.11", True),
            ("0.9", True),  # 0.9 sorts below 0.12 as numbers, above it as text
            ("0.12", False),
            ("0.12.1", False),
            ("0.15.1", False),
            ("1.0", False),
        ],
    )
    def test_typst_is_compared_as_numbers(self, version, expected):
        assert toolchain.too_old(toolchain.Tool("typst", "/typst", version)) is expected

    def test_a_version_that_could_not_be_read_is_not_called_old(self):
        # A program that answered --version with something unexpected still gets
        # to try: refusing to build over that would be worse than letting it.
        assert toolchain.too_old(toolchain.Tool("typst", "/typst", None)) is False

    def test_a_program_with_no_floor_is_never_old(self):
        assert toolchain.too_old(toolchain.Tool("sed", "/sed", "0.1")) is False


class TestRequire:
    def test_a_missing_program_says_how_to_install_it(self, monkeypatch):
        monkeypatch.setattr(toolchain, "find", lambda name: toolchain.Tool(name, None, None))
        with pytest.raises(ToolchainError, match="not installed") as caught:
            toolchain.require("typst")
        assert "brew install typst" in caught.value.hint

    def test_an_old_program_names_both_versions(self, monkeypatch):
        monkeypatch.setattr(
            toolchain, "find", lambda name: toolchain.Tool(name, "/typst", "0.11")
        )
        with pytest.raises(ToolchainError, match="too old") as caught:
            toolchain.require("typst")
        assert "0.11" in caught.value.message
        assert toolchain.MINIMUM["typst"] in caught.value.message

    def test_a_current_program_is_returned(self, monkeypatch):
        tool = toolchain.Tool("typst", "/typst", "0.15.1")
        monkeypatch.setattr(toolchain, "find", lambda name: tool)
        assert toolchain.require("typst") is tool


class TestRun:
    def test_a_wedged_program_stops_rather_than_hanging(self, monkeypatch):
        def wedge(*args, **kwargs):
            assert kwargs["timeout"] == toolchain.RUN_TIMEOUT
            raise subprocess.TimeoutExpired(cmd="typst", timeout=kwargs["timeout"])

        monkeypatch.setattr(subprocess, "run", wedge)
        with pytest.raises(ToolchainError, match="did not finish") as caught:
            toolchain.run(["typst", "compile", "document.typ"])
        # TimeoutExpired is a SubprocessError, not an OSError, so it is only
        # caught if it was given an arm of its own.
        assert "typst" in caught.value.message
        assert str(toolchain.RUN_TIMEOUT) in caught.value.message
