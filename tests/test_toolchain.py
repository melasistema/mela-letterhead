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


class TestAltText:
    @pytest.mark.parametrize(
        "version, expected",
        [
            ("3.1", False),  # what apt ships, and what CI tests on purpose
            ("3.1.11.1", False),
            ("3.9", False),
            # The fourth component is the whole of the difference here: the
            # Typst writer learnt to carry a description in 3.9.0.1, so 3.9.0
            # is the last release without it.
            ("3.9.0", False),
            ("3.9.0.1", True),
            ("3.9.1", True),
            ("3.11", True),
            ("4.0", True),
        ],
    )
    def test_the_floor_counts_every_component(self, version, expected):
        tool = toolchain.Tool("pandoc", "/pandoc", version)
        assert toolchain.carries_alt_text(tool) is expected

    def test_a_version_that_could_not_be_read_gets_the_benefit_of_the_doubt(self):
        # The same licence as `too_old`: let it try, and fail in Typst if it
        # must, rather than refuse the build over a guess.
        tool = toolchain.Tool("pandoc", "/pandoc", None)
        assert toolchain.carries_alt_text(tool) is True


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


class TestReadingAVersion:
    @pytest.mark.parametrize(
        "output, expected",
        [
            ("pandoc 3.11\nFeatures: +server\n", "3.11"),
            # Four components, and the last one is load-bearing — a pattern
            # that stopped at three would read this as 3.9.0 and call the
            # release too old for the feature it introduced.
            ("pandoc 3.9.0.1\n", "3.9.0.1"),
            ("typst 0.15.1 (unknown commit)\n", "0.15.1"),
            ("something with no number in it\n", None),
        ],
    )
    def test_however_many_components_it_has(self, monkeypatch, output, expected):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, output, ""),
        )
        assert toolchain._read_version("/pandoc") == expected


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
