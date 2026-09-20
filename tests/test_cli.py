"""The command line, and `check` in particular.

`check` is billed as the diagnostic of first resort, which is only true if it
settles everything `build` settles. It used to read the configuration and stop
there, so every colour, weight, length, footer row and header field passed it
and failed on the next command. These tests hold it to the larger promise.
"""

import shutil

import pytest

from mela_letterhead import __version__, cli, toolchain

needs_toolchain = pytest.mark.skipif(
    shutil.which("pandoc") is None or shutil.which("typst") is None,
    reason="pandoc and typst are both needed for a clean bill of health",
)

SOUND = """\
brand:
  name: Acme Studio
footer:
  columns:
    - title: Acme Studio
      rows:
        - ["Tel.", "+00 000"]
"""


def make_project(tmp_path, config=SOUND, documents=(("doc.md", "lang: en\n"),)):
    (tmp_path / "letterhead.yaml").write_text(config, encoding="utf-8")
    for name, front_matter in documents:
        (tmp_path / name).write_text(
            f"---\n{front_matter}---\n# Heading\n", encoding="utf-8"
        )
    return tmp_path


def check(tmp_path, capsys, **kwargs):
    """Run `check` against a project and return its exit code and output."""
    project = make_project(tmp_path, **kwargs)
    status = cli.main(["check", "-c", str(project / "letterhead.yaml")])
    return status, capsys.readouterr().out


class TestCheckResolvesTheLetterhead:
    @needs_toolchain
    def test_a_sound_letterhead_checks_out(self, tmp_path, capsys):
        status, out = check(tmp_path, capsys)
        assert status == 0
        assert "every setting resolves" in out
        assert "Everything checks out." in out

    def test_a_colour_that_is_not_one_is_caught(self, tmp_path, capsys):
        # The defect: `check` said everything checked out and exited 0, and
        # `build` refused this line immediately afterwards.
        status, out = check(
            tmp_path, capsys, config=SOUND + 'palette:\n  accent: "not-a-colour"\n'
        )
        assert status == 1
        assert "palette.accent" in out
        assert "every setting resolves" not in out

    def test_the_hint_is_printed_with_it(self, tmp_path, capsys):
        _, out = check(
            tmp_path, capsys, config=SOUND + 'palette:\n  accent: "not-a-colour"\n'
        )
        assert "#f5f5f7" in out

    def test_a_malformed_footer_row_is_named(self, tmp_path, capsys):
        config = SOUND.replace('        - ["Tel.", "+00 000"]\n', "        - [1, 2, 3]\n")
        status, out = check(tmp_path, capsys, config=config)
        assert status == 1
        assert "footer.columns[0].rows[0]" in out

    def test_a_weight_that_is_not_one_is_caught(self, tmp_path, capsys):
        config = SOUND.replace(
            "  name: Acme Studio\n",
            "  name: Acme Studio\n  wordmark:\n    weight: 1200\n",
        )
        status, out = check(tmp_path, capsys, config=config)
        assert status == 1
        assert "brand.wordmark.weight" in out

    def test_a_static_error_is_reported_once_not_once_per_document(
        self, tmp_path, capsys
    ):
        _, out = check(
            tmp_path,
            capsys,
            config=SOUND + 'palette:\n  accent: "not-a-colour"\n',
            documents=(("a.md", "lang: en\n"), ("b.md", "lang: en\n")),
        )
        assert out.count("palette.accent") == 1


class TestCheckResolvesEachDocument:
    def test_a_language_only_error_names_the_document_that_meets_it(
        self, tmp_path, capsys
    ):
        # A value written per language is only wrong in some of them, and the
        # document that declares that language is the one that cannot build.
        config = SOUND + 'header:\n  fill: { en: "#ffffff", it: "dark purple" }\n'
        status, out = check(
            tmp_path,
            capsys,
            config=config,
            documents=(("english.md", "lang: en\n"), ("italian.md", "lang: it\n")),
        )
        assert status == 1
        assert "italian.md" in out
        assert "header.fill" in out
        # The English document resolves, and says so rather than being tarred
        # with the Italian one's brush.
        assert "english.md" in out
        assert out.count("header.fill") == 1

    def test_a_document_whose_front_matter_is_broken_is_named(self, tmp_path, capsys):
        project = make_project(tmp_path)
        (project / "broken.md").write_text(
            '---\ntitle: Offer: phase two\n---\n\nBody.\n', encoding="utf-8"
        )
        status = cli.main(["check", "-c", str(project / "letterhead.yaml")])
        out = capsys.readouterr().out
        assert status == 1
        assert "broken.md" in out


class TestTheToolchainSection:
    def test_a_typst_too_old_is_a_problem_not_a_tick(self, tmp_path, capsys, monkeypatch):
        # The whole point of the floor: an old Typst used to fail inside
        # letterhead.typ, with a message about a name it had never heard of.
        monkeypatch.setattr(
            cli.toolchain,
            "find",
            lambda name: cli.toolchain.Tool(name, f"/{name}", "0.9"),
        )
        status, out = check(tmp_path, capsys)
        assert status == 1
        assert "too old" in out
        assert cli.toolchain.MINIMUM["typst"] in out


class TestColour:
    """`NO_COLOR` and `FORCE_COLOR`, asked per line rather than at import."""

    def test_nothing_is_painted_into_a_pipe(self, tmp_path, capsys, monkeypatch):
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        _, out = check(tmp_path, capsys)  # capsys is not a terminal
        assert "\033[" not in out

    def test_no_color_wins_over_a_terminal(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
        assert cli._bold("x") == "x"

    def test_no_color_is_read_by_presence_not_by_value(self, monkeypatch):
        # The convention: NO_COLOR=0 is still somebody asking for no colour.
        monkeypatch.setenv("NO_COLOR", "0")
        assert cli._bold("x") == "x"

    def test_an_empty_no_color_is_not_set_at_all(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "")
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert cli._bold("x") == "\033[1mx\033[0m"

    def test_force_color_paints_into_a_pipe(self, tmp_path, capsys, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        _, out = check(tmp_path, capsys)
        assert "\033[" in out


class Stream:
    """`sys.stdout` with an encoding of somebody else's choosing.

    Everything written still reaches the stream underneath, so `capsys` reads
    the output back as it always does; only the answer to `.encoding` changes.
    """

    def __init__(self, wrapped, encoding):
        self._wrapped = wrapped
        self.encoding = encoding

    def write(self, text):
        return self._wrapped.write(text)

    def flush(self):
        self._wrapped.flush()

    def isatty(self):
        return False


class TestMarksFitTheStream:
    """A tick is not printable everywhere, and `check` prints one per line.

    Windows gives a redirected command the ANSI code page rather than UTF-8,
    and cp1252 has no U+2713 in it: the whole command died in a
    `UnicodeEncodeError` on the first line of its own report.
    """

    @staticmethod
    def as_though(monkeypatch, encoding):
        monkeypatch.setattr(cli.sys, "stdout", Stream(cli.sys.stdout, encoding))

    def test_the_tick_and_the_cross_survive_a_code_page(self, monkeypatch):
        self.as_though(monkeypatch, "cp1252")
        for mark in (cli._tick(), cli._cross()):
            mark.encode("cp1252")  # the assertion is that this does not raise

    def test_a_stream_that_can_take_them_gets_them(self, monkeypatch):
        self.as_though(monkeypatch, "utf-8")
        assert "✓" in cli._tick()
        assert "✗" in cli._cross()

    def test_the_marks_keep_their_width_either_way(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        widths = set()
        for encoding in ("utf-8", "cp1252"):
            self.as_though(monkeypatch, encoding)
            widths.add((len(cli._tick()), len(cli._cross())))
        assert widths == {(1, 1)}

    def test_a_stream_with_no_encoding_at_all_falls_back(self, monkeypatch):
        # `sys.stdout` is whatever the caller put there, and not all of them
        # are text streams with an encoding to ask about.
        self.as_though(monkeypatch, None)
        assert cli._mark("✓", "+") == "+"

    def test_the_whole_report_is_printable_on_a_code_page(self, tmp_path, capsys, monkeypatch):
        self.as_though(monkeypatch, "cp1252")
        _, out = check(tmp_path, capsys)
        out.encode("cp1252")  # as the Windows console would have to


class TestCheckAndThePdfStandard:
    """What `check` can and cannot say about a standard.

    It compiles nothing, so conformance is not its to judge. The half that is
    about this machine rather than about the document — whether the Pandoc
    installed here carries a picture's description as far as the page — is,
    and it is the half that would otherwise be reported as the document's
    fault by a compiler two steps further on.
    """

    @needs_toolchain
    def test_the_standards_asked_for_are_reported(self, tmp_path, capsys):
        status, out = check(tmp_path, capsys, config=SOUND + "pdf:\n  standard: [a-3b]\n")
        assert "a-3b" in out
        assert status == 0

    @needs_toolchain
    def test_nothing_asked_for_says_nothing(self, tmp_path, capsys):
        _, out = check(tmp_path, capsys)
        assert "pdf standard" not in out

    def test_an_unknown_standard_is_a_problem(self, tmp_path, capsys):
        status, out = check(tmp_path, capsys, config=SOUND + "pdf:\n  standard: [a2b]\n")
        assert status == 1
        assert "pdf.standard" in out and "a-2b" in out

    def test_an_old_pandoc_is_a_problem_for_an_accessible_standard(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr(
            toolchain,
            "find",
            lambda name: toolchain.Tool(name, f"/{name}", "3.1" if name == "pandoc" else "0.15.1"),
        )
        status, out = check(tmp_path, capsys, config=SOUND + "pdf:\n  standard: [ua-1]\n")
        assert status == 1
        assert "pdf.standard" in out
        assert toolchain.PANDOC_ALT_TEXT in out

    def test_the_same_pandoc_is_no_problem_for_an_archival_one(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr(
            toolchain,
            "find",
            lambda name: toolchain.Tool(name, f"/{name}", "3.1" if name == "pandoc" else "0.15.1"),
        )
        _, out = check(tmp_path, capsys, config=SOUND + "pdf:\n  standard: [a-3b]\n")
        assert toolchain.PANDOC_ALT_TEXT not in out


class TestCheckFindsTheFilesTheLetterheadNames:
    """The logo and the background are the two pictures `check` looks for.

    Both are read relative to `letterhead.yaml` rather than to the document,
    and both may be written per language — so these go through the same
    resolution a build would, and a missing one is a problem rather than a
    stack trace at compile time.
    """

    def test_a_logo_that_is_not_there_is_a_problem(self, tmp_path, capsys):
        config = SOUND.replace("  name: Acme Studio\n", "  name: Acme Studio\n  logo: mark.svg\n")
        status, out = check(tmp_path, capsys, config=config)
        assert status == 1
        assert "logo not found" in out
        assert "mark.svg" in out

    def test_a_background_that_is_not_there_is_a_problem(self, tmp_path, capsys):
        config = SOUND + "page:\n  background:\n    image: sheet.png\n"
        status, out = check(tmp_path, capsys, config=config)
        assert status == 1
        assert "background not found" in out
        assert "sheet.png" in out

    @needs_toolchain
    def test_a_letterhead_with_no_logo_says_so_rather_than_failing(self, tmp_path, capsys):
        # A brand name with no mark is a finished letterhead, not a fallback.
        status, out = check(tmp_path, capsys)
        assert status == 0
        assert "wordmark" in out


class TestCheckWithNoDocuments:
    @needs_toolchain
    def test_matching_nothing_is_reported_but_is_not_a_problem(self, tmp_path, capsys):
        # An empty project is a project somebody has just scaffolded. It has
        # nothing to build and nothing wrong with it.
        project = make_project(tmp_path, documents=())
        status = cli.main(["check", "-c", str(project / "letterhead.yaml")])
        out = capsys.readouterr().out
        assert status == 0
        assert "none found" in out


class TestInit:
    def test_every_file_lands(self, tmp_path):
        assert cli.main(["init", str(tmp_path)]) == 0
        assert (tmp_path / "letterhead.yaml").is_file()
        assert (tmp_path / "example-letter.md").is_file()
        assert (tmp_path / "assets" / "logo.svg").is_file()
        for plate in cli.SCAFFOLD_PLATES:
            assert (tmp_path / "assets" / plate).is_file()

    def test_the_scaffold_it_writes_is_the_one_that_ships(self, tmp_path):
        # Not a copy kept in the tests: what `init` writes has to be what is
        # in the package, or the wheel can ship without its plates and no test
        # would notice.
        cli.main(["init", str(tmp_path)])
        written = (tmp_path / "letterhead.yaml").read_bytes()
        assert written == (cli.SCAFFOLD / "letterhead.yaml").read_bytes()

    def test_it_will_not_overwrite_what_is_already_there(self, tmp_path, capsys):
        (tmp_path / "letterhead.yaml").write_text("mine\n", encoding="utf-8")
        status = cli.main(["init", str(tmp_path)])
        out = capsys.readouterr().out
        assert status == 1
        assert "already exist" in out
        # Nothing written at all, not even the files that were not in the way.
        assert (tmp_path / "letterhead.yaml").read_text(encoding="utf-8") == "mine\n"
        assert not (tmp_path / "example-letter.md").exists()

    def test_force_overwrites(self, tmp_path):
        (tmp_path / "letterhead.yaml").write_text("mine\n", encoding="utf-8")
        assert cli.main(["init", str(tmp_path), "--force"]) == 0
        assert "mine" not in (tmp_path / "letterhead.yaml").read_text(encoding="utf-8")
        assert (tmp_path / "example-letter.md").is_file()

    def test_a_directory_that_does_not_exist_yet_is_made(self, tmp_path):
        assert cli.main(["init", str(tmp_path / "new" / "deeper")]) == 0
        assert (tmp_path / "new" / "deeper" / "letterhead.yaml").is_file()


class TestBuild:
    def test_a_document_that_is_not_there_is_reported_not_raised(self, tmp_path, capsys):
        project = make_project(tmp_path)
        status = cli.main(
            ["build", str(project / "nope.md"), "-c", str(project / "letterhead.yaml")]
        )
        assert status == 1
        # On stderr, because this one stops the command rather than being a
        # line in a report.
        assert "nope.md" in capsys.readouterr().err

    def test_a_configuration_that_is_not_there_is_reported_not_raised(self, tmp_path, capsys):
        assert cli.main(["build", "-c", str(tmp_path / "nope.yaml")]) == 1
        assert capsys.readouterr().err


class TestParser:
    def test_no_command_prints_help(self, capsys):
        assert cli.main([]) == 0
        assert "mela-letterhead" in capsys.readouterr().out

    def test_version_is_printed_and_nothing_is_built(self, capsys):
        with pytest.raises(SystemExit) as caught:
            cli.main(["--version"])
        assert caught.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_a_configuration_that_is_not_there_is_reported_not_raised(self, tmp_path):
        assert cli.main(["check", "-c", str(tmp_path / "nope.yaml")]) == 1
