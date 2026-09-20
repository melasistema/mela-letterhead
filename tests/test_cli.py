"""The command line, and `check` in particular.

`check` is billed as the diagnostic of first resort, which is only true if it
settles everything `build` settles. It used to read the configuration and stop
there, so every colour, weight, length, footer row and header field passed it
and failed on the next command. These tests hold it to the larger promise.
"""

import os
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


class TestTheSchemaTravelsWithTheProject:
    """The letterhead's first line names a file, so the file has to be there.

    Nothing here reaches the network, and that is the point: the schema is
    carried in the package, copied into the project, and read off the disk by
    whatever editor the user has. A URL would be a file to serve forever and a
    red underline in every editor on the day it stopped resolving.
    """

    def test_init_writes_it(self, tmp_path):
        cli.main(["init", str(tmp_path)])
        written = tmp_path / cli.SCHEMA_FILENAME
        assert written.is_file()
        assert written.read_bytes() == cli.SCHEMA_SOURCE.read_bytes()

    def test_the_scaffold_points_at_it_by_a_relative_path(self, tmp_path):
        # The two have to agree on the name, and the path has to stay relative:
        # an absolute one breaks the moment the project is moved or shared.
        cli.main(["init", str(tmp_path)])
        first = (tmp_path / "letterhead.yaml").read_text(encoding="utf-8").splitlines()[0]
        assert first == f"# yaml-language-server: $schema={cli.SCHEMA_FILENAME}"

    def test_what_the_scaffold_names_is_what_lands(self, tmp_path):
        cli.main(["init", str(tmp_path)])
        text = (tmp_path / "letterhead.yaml").read_text(encoding="utf-8")
        modeline = text.splitlines()[0]
        named = modeline.split("$schema=", 1)[1].strip()
        assert (tmp_path / named).is_file()

    def test_the_schema_command_writes_it_into_a_bare_directory(self, tmp_path, capsys):
        assert cli.main(["schema", str(tmp_path)]) == 0
        assert (tmp_path / cli.SCHEMA_FILENAME).is_file()
        assert "created" in capsys.readouterr().out

    def test_it_refreshes_a_copy_from_another_version(self, tmp_path, capsys):
        stale = tmp_path / cli.SCHEMA_FILENAME
        stale.write_text('{"title": "from 0.4.0"}\n', encoding="utf-8")
        assert cli.main(["schema", str(tmp_path)]) == 0
        assert stale.read_bytes() == cli.SCHEMA_SOURCE.read_bytes()
        assert "updated" in capsys.readouterr().out

    def test_it_says_so_when_there_was_nothing_to_do(self, tmp_path, capsys):
        cli.main(["schema", str(tmp_path)])
        capsys.readouterr()
        assert cli.main(["schema", str(tmp_path)]) == 0
        assert "already this version's" in capsys.readouterr().out

    def test_an_old_project_is_told_the_line_to_add(self, tmp_path, capsys):
        # A letterhead written before the schema existed has no modeline, and
        # the file alone does nothing without one.
        (tmp_path / "letterhead.yaml").write_text(SOUND, encoding="utf-8")
        cli.main(["schema", str(tmp_path)])
        out = capsys.readouterr().out
        assert "does not point at it yet" in out
        assert f"$schema={cli.SCHEMA_FILENAME}" in out

    def test_a_letterhead_already_pointed_somewhere_is_left_alone(self, tmp_path, capsys):
        (tmp_path / "letterhead.yaml").write_text(
            "# yaml-language-server: $schema=../shared/ours.json\n" + SOUND,
            encoding="utf-8",
        )
        cli.main(["schema", str(tmp_path)])
        assert "does not point at it yet" not in capsys.readouterr().out

    def test_a_directory_that_does_not_exist_yet_is_made(self, tmp_path):
        assert cli.main(["schema", str(tmp_path / "new")]) == 0
        assert (tmp_path / "new" / cli.SCHEMA_FILENAME).is_file()


class TestCheckAndTheProjectSchema:
    def test_a_stale_copy_is_reported(self, tmp_path, capsys):
        project = make_project(tmp_path)
        (project / cli.SCHEMA_FILENAME).write_text('{"title": "old"}\n', encoding="utf-8")
        cli.main(["check", "-c", str(project / "letterhead.yaml")])
        out = capsys.readouterr().out
        assert "written by another version" in out
        assert "mela-letterhead schema" in out

    @needs_toolchain
    def test_saying_so_does_not_fail_the_run(self, tmp_path, capsys):
        # An editor's convenience, not an input to the page: saying so must not
        # turn a sound letterhead into a failing one. Split from the test above
        # so that the report itself is still checked on a machine with no
        # toolchain, where `check` exits 1 for reasons of its own.
        project = make_project(tmp_path)
        (project / cli.SCHEMA_FILENAME).write_text('{"title": "old"}\n', encoding="utf-8")
        assert cli.main(["check", "-c", str(project / "letterhead.yaml")]) == 0

    def test_a_current_copy_says_nothing(self, tmp_path, capsys):
        project = make_project(tmp_path)
        shutil.copy2(cli.SCHEMA_SOURCE, project / cli.SCHEMA_FILENAME)
        cli.main(["check", "-c", str(project / "letterhead.yaml")])
        assert "written by another version" not in capsys.readouterr().out

    def test_a_project_without_one_is_not_nagged(self, tmp_path, capsys):
        project = make_project(tmp_path)
        cli.main(["check", "-c", str(project / "letterhead.yaml")])
        out = capsys.readouterr().out
        assert "schema" not in out.lower()


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


PROFILED = SOUND + """\
profiles:
  draft:
    palette:
      accent: "#a4262c"
  final:
    palette:
      accent: "#000000"
"""


class TestCheckAndProfiles:
    """The half of this feature that is easy to forget.

    The failure a per-document override will actually have is being silently
    not applied, so `check` is where it has to become visible.
    """

    @needs_toolchain
    def test_the_profiles_a_letterhead_defines_are_listed(self, tmp_path, capsys):
        status, out = check(tmp_path, capsys, config=PROFILED)
        assert status == 0
        assert "draft, final" in out

    @needs_toolchain
    def test_the_active_profile_says_where_it_came_from(self, tmp_path, capsys):
        project = make_project(tmp_path, config=PROFILED)
        status = cli.main(
            ["check", "-c", str(project / "letterhead.yaml"), "--profile", "draft"]
        )
        out = capsys.readouterr().out
        assert status == 0
        assert "profile        draft" in out
        assert "from --profile" in out

    @needs_toolchain
    def test_a_document_carrying_overrides_is_marked(self, tmp_path, capsys):
        status, out = check(
            tmp_path,
            capsys,
            config=PROFILED,
            documents=(
                (
                    "doc.md",
                    "lang: en\nprofile: draft\n"
                    "letterhead:\n  palette:\n    ink: '#111111'\n"
                    "  footer:\n    show: false\n",
                ),
            ),
        )
        assert status == 0
        assert "profile draft" in out
        assert "+2 overrides" in out

    @needs_toolchain
    def test_a_document_with_nothing_of_its_own_is_not_marked(self, tmp_path, capsys):
        _, out = check(tmp_path, capsys, config=PROFILED)
        assert "override" not in out

    def test_an_unknown_profile_is_refused_once_with_a_suggestion(self, tmp_path, capsys):
        project = make_project(tmp_path, config=PROFILED)
        status = cli.main(
            ["check", "-c", str(project / "letterhead.yaml"), "--profile", "finl"]
        )
        out = capsys.readouterr().out
        assert status == 1
        assert "unknown profile" in out
        assert "final" in out
        # Once, against the letterhead — not once for every document.
        assert out.count("unknown profile") == 1

    def test_a_block_that_is_not_a_mapping_is_named_with_its_document(
        self, tmp_path, capsys
    ):
        status, out = check(
            tmp_path,
            capsys,
            config=PROFILED,
            documents=(("doc.md", "lang: en\nletterhead: nothing\n"),),
        )
        assert status == 1
        assert "doc.md" in out and "letterhead" in out

    def test_a_setting_only_the_profile_gets_wrong_is_caught(self, tmp_path, capsys):
        # `check` resolves what `build` resolves, profile and all, or it is not
        # the diagnostic of first resort it is billed as.
        config = SOUND + "profiles:\n  draft:\n    palette:\n      accent: dark red\n"
        project = make_project(tmp_path, config=config)
        status = cli.main(
            ["check", "-c", str(project / "letterhead.yaml"), "--profile", "draft"]
        )
        out = capsys.readouterr().out
        assert status == 1
        assert "palette.accent" in out

    @needs_toolchain
    def test_and_the_same_letterhead_without_it_is_sound(self, tmp_path, capsys):
        # The other half of the test above: what the profile breaks, only the
        # profile breaks. Marked because a clean bill of health needs the
        # toolchain, while being told what is wrong does not.
        config = SOUND + "profiles:\n  draft:\n    palette:\n      accent: dark red\n"
        project = make_project(tmp_path, config=config)
        assert cli.main(["check", "-c", str(project / "letterhead.yaml")]) == 0


class TestWatchSignatures:
    """The decidable half of watching, lifted out of the loop.

    A signature is the modification time *and* the size, because some
    filesystems carry the time to the second and saving twice inside one second
    is the commonest edit there is.
    """

    def test_a_touched_file_is_seen(self, tmp_path):
        path = tmp_path / "doc.md"
        path.write_text("one\n", encoding="utf-8")
        before = cli._watch_signature([path])
        os.utime(path, (2_000_000_000, 2_000_000_000))
        assert cli._changed(before, cli._watch_signature([path])) == {path}

    def test_a_save_inside_the_same_second_is_seen_by_its_size(self, tmp_path):
        path = tmp_path / "doc.md"
        path.write_text("one\n", encoding="utf-8")
        os.utime(path, (2_000_000_000, 2_000_000_000))
        before = cli._watch_signature([path])
        path.write_text("one and a half\n", encoding="utf-8")
        os.utime(path, (2_000_000_000, 2_000_000_000))  # the clock has not moved
        assert cli._changed(before, cli._watch_signature([path])) == {path}

    def test_a_deleted_file_is_a_change(self, tmp_path):
        path = tmp_path / "doc.md"
        path.write_text("one\n", encoding="utf-8")
        before = cli._watch_signature([path])
        path.unlink()
        assert cli._changed(before, cli._watch_signature([path])) == {path}

    def test_a_file_that_is_not_there_is_simply_left_out(self, tmp_path):
        assert cli._watch_signature([tmp_path / "nothing.md"]) == {}

    def test_a_file_that_appears_is_a_change(self, tmp_path):
        # The other half of the rule above, and what makes a newly written
        # document rebuild without being named: a path that was not there is
        # left out of the signature, so arriving in it is a difference. Nothing
        # here reads the directory's own modification time — POSIX moves that
        # when an entry is added and Windows does not, and a feature resting on
        # it would have worked on two platforms out of three.
        path = tmp_path / "new.md"
        before = cli._watch_signature([path])
        path.write_text("new\n", encoding="utf-8")
        assert cli._changed(before, cli._watch_signature([path])) == {path}

    def test_nothing_moving_is_no_change(self, tmp_path):
        path = tmp_path / "doc.md"
        path.write_text("one\n", encoding="utf-8")
        signature = cli._watch_signature([path])
        assert cli._changed(signature, cli._watch_signature([path])) == set()


class TestWhatIsWatched:
    def test_the_letterhead_its_documents_and_their_pictures(self, tmp_path):
        project = make_project(tmp_path)
        (project / "mark.svg").write_text("<svg/>", encoding="utf-8")
        config_path = project / "letterhead.yaml"
        config_path.write_text(
            SOUND.replace("  name: Acme Studio\n", "  name: Acme Studio\n  logo: mark.svg\n"),
            encoding="utf-8",
        )
        config = cli.config_module.load(config_path)

        plate = project / "plate.svg"
        result = cli.builder.BuildResult(
            document=None, pdf=project / "doc.pdf", language="en", inputs=(plate,)
        )
        watched = cli._watched(config, None, [result])

        assert config_path in watched
        assert project / "mark.svg" in watched
        assert project / "doc.md" in watched
        assert plate in watched
        # The source directory itself, so that creating one that is not there
        # counts as a change.
        assert config.source_dir in watched

    def test_a_document_written_since_the_last_pass_is_found(self, tmp_path):
        # Discovery is re-asked every pass, which is what picks up a document
        # written while the watch is running. The directory's modification time
        # is no part of it.
        project = make_project(tmp_path)
        config = cli.config_module.load(project / "letterhead.yaml")
        assert project / "later.md" not in cli._watched(config, None, [])
        (project / "later.md").write_text("lang: en\n", encoding="utf-8")
        assert project / "later.md" in cli._watched(config, None, [])

    def test_a_named_document_is_watched_and_its_neighbours_are_not(self, tmp_path):
        project = make_project(
            tmp_path, documents=(("one.md", "lang: en\n"), ("two.md", "lang: en\n"))
        )
        config = cli.config_module.load(project / "letterhead.yaml")
        watched = cli._watched(config, [project / "one.md"], [])
        assert (project / "one.md").resolve() in watched
        assert (project / "two.md").resolve() not in watched

    def test_a_logo_written_per_language_is_resolved_first(self, tmp_path):
        # Read straight out of `config.data` the language map would stringify
        # into a path nothing can stat.
        config_path = tmp_path / "letterhead.yaml"
        config_path.write_text(
            SOUND.replace(
                "  name: Acme Studio\n",
                "  name: Acme Studio\n  logo: { en: mark-en.svg, de: mark-de.svg }\n",
            ),
            encoding="utf-8",
        )
        config = cli.config_module.load(config_path)
        assert tmp_path / "mark-en.svg" in cli._watched(config, None, [])

    def test_a_source_directory_that_is_not_there_is_still_watched(self, tmp_path):
        # Creating it is how the user fixes the error the build just reported.
        config_path = tmp_path / "letterhead.yaml"
        config_path.write_text(SOUND + "documents:\n  source: letters\n", encoding="utf-8")
        config = cli.config_module.load(config_path)
        assert cli._watched(config, None, []) == [config_path, tmp_path / "letters"]


class TestWatchLoop:
    """The loop itself, driven by a fake clock rather than by waiting.

    Every call to `sleep` moves a file on, so the poll always finds something
    and the loop advances a pass; the build is faked, because what is under
    test is what the loop does with its result.
    """

    @staticmethod
    def run_watch(tmp_path, monkeypatch, build, on_sleep=None):
        project = make_project(tmp_path)
        moved = project / "doc.md"
        clock = {"t": 2_000_000_000, "waits": 0}

        def sleep(_seconds):
            clock["waits"] += 1
            clock["t"] += 1
            if on_sleep is not None:
                on_sleep(project, clock["waits"])
            os.utime(moved, (clock["t"], clock["t"]))

        monkeypatch.setattr(cli.time, "sleep", sleep)
        monkeypatch.setattr(cli, "_build_once", build)
        return cli.main(["build", "--watch", "-c", str(project / "letterhead.yaml")])

    def test_it_builds_again_until_it_is_interrupted(self, tmp_path, monkeypatch):
        calls = []

        def build(config, sources, keep_build, profile=None):
            calls.append(config)
            if len(calls) == 3:
                raise KeyboardInterrupt
            return []

        # Ctrl-C is how a watch ends, so it is not a failure. A one-shot build
        # interrupted halfway still returns 130.
        assert self.run_watch(tmp_path, monkeypatch, build) == 0
        assert len(calls) == 3  # the first build and two rebuilds

    def test_a_failed_build_does_not_end_the_session(self, tmp_path, monkeypatch, capsys):
        # The whole value of watching: you fix the error and watch it go away.
        calls = []

        def build(config, sources, keep_build, profile=None):
            calls.append(config)
            if len(calls) == 2:
                raise cli.LetterheadError("plate.svg: no such picture")
            if len(calls) == 4:
                raise KeyboardInterrupt
            return []

        assert self.run_watch(tmp_path, monkeypatch, build) == 0
        assert len(calls) == 4
        assert "no such picture" in capsys.readouterr().err

    def test_editing_the_letterhead_reloads_it(self, tmp_path, monkeypatch):
        calls = []

        def build(config, sources, keep_build, profile=None):
            calls.append(config)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return []

        def edit(project, wait):
            if wait == 1:
                (project / "letterhead.yaml").write_text(
                    SOUND.replace("Acme Studio", "Acme Works"), encoding="utf-8"
                )

        assert self.run_watch(tmp_path, monkeypatch, build, on_sleep=edit) == 0
        assert calls[0].data["brand"]["name"] == "Acme Studio"
        assert calls[1].data["brand"]["name"] == "Acme Works"

    def test_a_letterhead_that_stops_reading_keeps_the_old_one(
        self, tmp_path, monkeypatch, capsys
    ):
        # Half-typed YAML is a thing to be told about, not a thing to be
        # thrown out of the session for.
        calls = []

        def build(config, sources, keep_build, profile=None):
            calls.append(config)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return []

        def edit(project, wait):
            if wait == 1:
                (project / "letterhead.yaml").write_text("brand: [\n", encoding="utf-8")
            elif wait == 3:
                (project / "letterhead.yaml").write_text(SOUND, encoding="utf-8")

        assert self.run_watch(tmp_path, monkeypatch, build, on_sleep=edit) == 0
        # Two builds: the first, and the one after the file read again. The
        # pass in between reported the error and built nothing.
        assert len(calls) == 2
        assert "letterhead.yaml" in capsys.readouterr().err


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
