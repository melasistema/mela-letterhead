"""End-to-end builds.

These run the real Pandoc and the real Typst, and are skipped when either is
missing, so a contributor without the toolchain can still run the rest.
"""

import json
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from mela_letterhead import builder, cli, toolchain
from mela_letterhead import config as config_module
from mela_letterhead.builder import ASSETS
from mela_letterhead.document import Document
from mela_letterhead.errors import BuildError, ConfigError

SCAFFOLD = ASSETS / "scaffold"

needs_toolchain = pytest.mark.skipif(
    shutil.which("pandoc") is None or shutil.which("typst") is None,
    reason="pandoc and typst are both needed for an end-to-end build",
)

# A standard that wants every picture described cannot be built by a Pandoc
# below 3.9.0.1, which drops the descriptions on the way — and `builder`
# refuses it up front rather than letting Typst report a document as missing
# what it has. That refusal is the feature, asserted in `TestAltTextSupport`;
# what it means here is that a test *asking* for such a standard needs a Pandoc
# that can deliver one, and says so instead of failing.
#
# This is not a corner case. The Linux CI job installs apt's Pandoc 3.1 on
# purpose, because that is what Debian users get, so these skip there — and run
# on the macOS and Windows jobs, which install a current release. A Pandoc that
# will not answer `--version` is given the benefit of the doubt, the same way
# `carries_alt_text` gives it.
needs_alt_text = pytest.mark.skipif(
    not toolchain.carries_alt_text(toolchain.find("pandoc")),
    reason=(
        f"pandoc {toolchain.PANDOC_ALT_TEXT} or newer is needed to carry a "
        "picture's description as far as the page"
    ),
)


def _permissions_bite():
    """Whether taking write permission away actually stops this process.

    Asked rather than assumed, because two ordinary situations answer no.
    Windows carries no POSIX mode bits — `chmod` there toggles a read-only flag
    and does not apply to a directory at all — and root is refused nothing
    anywhere. A test that asserted a refusal would then fail for the platform
    rather than for the code, and the Windows job runs this suite.
    """
    with tempfile.TemporaryDirectory() as temp:
        locked = Path(temp) / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        try:
            (locked / "probe").mkdir()
        except OSError:
            return True
        finally:
            locked.chmod(0o700)
    return False


needs_real_permissions = pytest.mark.skipif(
    not _permissions_bite(),
    reason="a directory cannot be made unwritable here (Windows, or running as root)",
)


@pytest.fixture
def project(tmp_path):
    """The scaffolded project, exactly as `mela-letterhead init` writes it."""
    shutil.copy2(SCAFFOLD / "letterhead.yaml", tmp_path / "letterhead.yaml")
    (tmp_path / "assets").mkdir()
    shutil.copy2(SCAFFOLD / "logo.svg", tmp_path / "assets" / "logo.svg")
    for plate in cli.SCAFFOLD_PLATES:
        shutil.copy2(SCAFFOLD / plate, tmp_path / "assets" / plate)
    shutil.copy2(SCAFFOLD / "example-letter.md", tmp_path / "example-letter.md")
    return tmp_path


@needs_toolchain
class TestBuild:
    def test_the_scaffold_builds(self, project):
        config = config_module.load(project / "letterhead.yaml")
        results = builder.build_all(config)
        assert len(results) == 1
        pdf = results[0].pdf
        assert pdf.name == "example-letter.pdf"
        assert pdf.read_bytes().startswith(b"%PDF")

    def test_intermediates_are_removed_by_default(self, project):
        config = config_module.load(project / "letterhead.yaml")
        builder.build_all(config)
        assert not (config.build_dir / "example-letter").exists()

    def test_keep_build_leaves_everything_it_handed_to_typst(self, project):
        config = config_module.load(project / "letterhead.yaml")
        builder.build_all(config, keep_build=True)
        workdir = config.build_dir / "example-letter"
        for name in ("document.json", "document.typ", "body.prep.md", "letterhead.typ", "logo.svg"):
            assert (workdir / name).is_file(), name
        # The plates the example prints, copied in beside the rest: Typst
        # compiles with its root here and can read nothing above it.
        placed = sorted(path.name for path in (workdir / builder.IMAGE_DIR).iterdir())
        assert placed == sorted(cli.SCAFFOLD_PLATES)

    def test_the_result_names_every_file_that_fed_the_build(self, project):
        # What `--watch` is watching. Which pictures a document uses is only
        # knowable after Pandoc has run, so a build is the only thing that can
        # say; the logo and the document itself come from the staging before it.
        config = config_module.load(project / "letterhead.yaml")
        (result,) = builder.build_all(config)
        assert sorted(path.name for path in result.inputs) == sorted(
            ["example-letter.md", "logo.svg", *cli.SCAFFOLD_PLATES]
        )
        # The paths on the user's disk, not the copies in the build directory,
        # which is the only form of any use to something watching for a change.
        for path in result.inputs:
            assert path.is_file()
            assert config.build_dir not in path.parents

    def test_a_picture_used_twice_is_named_once(self, project):
        (project / "twice.md").write_text(
            "# Twice\n\n![](assets/plate-condition.svg)\n\n"
            "![](./assets/plate-condition.svg)\n",
            encoding="utf-8",
        )
        config = config_module.load(project / "letterhead.yaml")
        result = builder.build_document(config, project / "twice.md")
        assert len(result.inputs) == len(set(result.inputs))

    def test_a_document_chooses_its_own_language(self, project):
        (project / "locales").mkdir()
        (project / "locales" / "de.yaml").write_text(
            "running_header: '{title} · Seite {page} von {pages}'\n", encoding="utf-8"
        )
        (project / "angebot.md").write_text(
            "---\ntitle: Angebot\nlang: de\ntype: Angebot\n---\n# Angebot\n\nText.\n",
            encoding="utf-8",
        )
        config = config_module.load(project / "letterhead.yaml")
        results = builder.build_all(config, [project / "angebot.md"], keep_build=True)

        assert results[0].language == "de"
        resolved = json.loads(
            (config.build_dir / "angebot" / "document.json").read_text(encoding="utf-8")
        )
        assert resolved["document"]["lang"] == "de"
        assert "Seite" in resolved["running"]["text"]
        assert resolved["header"]["fields"]["items"][0]["label"] == "Art:"

    def test_a_brand_with_no_logo_still_prints(self, project):
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        (project / "letterhead.yaml").write_text(
            text.replace("  logo: assets/logo.svg\n", ""), encoding="utf-8"
        )
        config = config_module.load(project / "letterhead.yaml")
        results = builder.build_all(config)
        assert results[0].pdf.read_bytes().startswith(b"%PDF")

    def test_a_brand_may_have_a_mark_per_market(self, project):
        # The logo is a string like any other, so it may be written once per
        # language — and it is staged in the document's language, not in the
        # printed form of the mapping.
        shutil.copy2(SCAFFOLD / "plate-condition.svg", project / "assets" / "logo-it.svg")
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        (project / "letterhead.yaml").write_text(
            text.replace(
                "  logo: assets/logo.svg\n",
                "  logo: { en: assets/logo.svg, it: assets/logo-it.svg }\n",
            ),
            encoding="utf-8",
        )
        (project / "offerta.md").write_text(
            "---\ntitle: Offerta\nlang: it\n---\n# Offerta\n\nTesto.\n", encoding="utf-8"
        )
        config = config_module.load(project / "letterhead.yaml")
        builder.build_all(config, [project / "offerta.md"], keep_build=True)
        staged = (config.build_dir / "offerta" / "logo.svg").read_bytes()
        assert staged == (project / "assets" / "logo-it.svg").read_bytes()

    def test_a_wordmark_a_coloured_band_and_a_border_compile_together(self, project):
        # The three ways a letterhead is made to look like somebody's own
        # without an image anywhere in it.
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        text = text.replace("  logo: assets/logo.svg\n", "")
        text = text.replace(
            "header:\n  show: true\n",
            'header:\n  show: true\n  fill: "#2b2440"\n  ink: "#f3f1fa"\n'
            '  muted: "#9d95bd"\n  rule_color: "#7a63d4"\n',
        )
        text = text.replace(
            "footer:\n  show: true\n",
            'footer:\n  show: true\n  fill: "#2b2440"\n  ink: "#f3f1fa"\n'
            '  highlight: "#ffb4a2"\n',
        )
        text = text.replace(
            "  margin:\n",
            "  border:\n    width: 2.4pt\n    sides: left\n    inset: 9mm\n  margin:\n",
        )
        text = text.replace(
            "brand:\n  name: Acme Studio\n",
            "brand:\n  name: Acme Studio\n  wordmark:\n    size: 34pt\n    weight: 300\n",
        )
        (project / "letterhead.yaml").write_text(text, encoding="utf-8")

        config = config_module.load(project / "letterhead.yaml")
        results = builder.build_all(config, keep_build=True)
        assert results[0].pdf.read_bytes().startswith(b"%PDF")

        resolved = json.loads(
            (config.build_dir / "example-letter" / "document.json").read_text(
                encoding="utf-8"
            )
        )
        # Pale on the band, and readable on the bare paper of page two.
        assert resolved["brand"]["wordmark"]["color"] == "#f3f1fa"
        assert resolved["brand"]["wordmark"]["running_color"] == resolved["palette"]["ink"]
        # The quotations are not dragged along by the header band.
        assert resolved["palette"]["band"] == "#f5f5f7"

    def test_a_designed_sheet_carries_the_document(self, project):
        # The tool turned around: no band of its own, a picture of paper
        # somebody designed elsewhere, and Markdown set on top of it.
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        text = text.replace("header:\n  show: true\n", "header:\n  show: false\n")
        text = text.replace("footer:\n  show: true\n", "footer:\n  show: false\n")
        text = text.replace("  show: true\n  logo_width", "  show: false\n  logo_width")
        text = text.replace(
            "  margin:\n",
            "  background:\n    image: assets/plate-roof-plan.svg\n"
            "    pages: all\n    veil: 35%\n  margin:\n",
        )
        (project / "letterhead.yaml").write_text(text, encoding="utf-8")

        config = config_module.load(project / "letterhead.yaml")
        results = builder.build_all(config, keep_build=True)
        assert results[0].pdf.read_bytes().startswith(b"%PDF")

        workdir = config.build_dir / "example-letter"
        assert (workdir / "background.svg").is_file()
        resolved = json.loads(
            (workdir / "document.json").read_text(encoding="utf-8")
        )
        # The staged name, not the path the user wrote: Typst compiles with its
        # root in the build directory and can read nothing above it.
        assert resolved["page"]["background"]["image"] == "background.svg"
        assert resolved["page"]["background"]["veil"] == pytest.approx(0.35)
        # With no header band, nothing pushes the first page down.
        assert resolved["page"]["first_page_extra"] == 0

    def test_the_spellings_of_older_pandoc_still_compile(self, project):
        # Debian and Ubuntu ship Pandoc 3.1, whose Typst writer emits
        # `#blockquote[...]` and `#horizontalrule` where 3.11 emits
        # `#quote(block: true)[...]` and `#divider`. The Pandoc template
        # polyfills the older names; this is what proves it without an older
        # Pandoc to hand.
        config = config_module.load(project / "letterhead.yaml")
        builder.build_all(config, keep_build=True)
        workdir = config.build_dir / "example-letter"
        generated = workdir / "document.typ"
        old_style = generated.read_text(encoding="utf-8").replace(
            "#quote(block: true)[", "#blockquote["
        )
        assert "#blockquote[" in old_style, "the scaffold no longer has a block quotation"
        generated.write_text(old_style + "\n#horizontalrule\n", encoding="utf-8")

        pdf = workdir / "older-pandoc.pdf"
        builder._run_typst(config, workdir, generated, pdf)
        assert pdf.read_bytes().startswith(b"%PDF")

    def test_output_goes_where_the_configuration_says(self, project):
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        (project / "letterhead.yaml").write_text(
            text.replace("  output: .", "  output: pdf"), encoding="utf-8"
        )
        config = config_module.load(project / "letterhead.yaml")
        results = builder.build_all(config)
        assert results[0].pdf.parent.name == "pdf"


@needs_toolchain
class TestReproducibleBuilds:
    """The same source, twice, byte for byte.

    It belongs beside PDF/A: an archival document that differs between two
    builds of the same source is an awkward thing to defend. Nothing in
    `builder` implements this — `toolchain.run` passes the environment straight
    through and Typst reads `SOURCE_DATE_EPOCH` from it — so what is under test
    is that nothing in the pipeline has started stamping the page itself.
    """

    def build(self, project, monkeypatch, epoch="1700000000"):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", epoch)
        config = config_module.load(project / "letterhead.yaml")
        return builder.build_all(config)[0].pdf.read_bytes()

    def test_a_fixed_timestamp_gives_a_fixed_file(self, project, monkeypatch):
        assert self.build(project, monkeypatch) == self.build(project, monkeypatch)

    def test_the_timestamp_really_is_in_the_file(self, project, monkeypatch):
        # Otherwise the test above would pass just as well on a build that
        # ignored the variable. Asserted by moving the clock rather than by
        # waiting for it: two builds a second apart are identical anyway,
        # because the stamp has one-second resolution — which is exactly what
        # makes the unfixed case awkward to reason about rather than obvious.
        assert self.build(project, monkeypatch, "1700000000") != self.build(
            project, monkeypatch, "1800000000"
        )


@needs_toolchain
class TestPdfStandards:
    """The scaffold, compiled to each standard it claims to reach.

    The claim is that a letterhead written this way can be filed, so these
    build the document that `init` writes rather than a stripped-down one: the
    two bands, the links in the footer, three drawings and a table are exactly
    what a standard has something to say about.
    """

    def build(self, project, standard):
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        assert "  standard: []" in text, "the scaffold no longer has an empty pdf.standard"
        (project / "letterhead.yaml").write_text(
            text.replace("  standard: []", f"  standard: {standard}"), encoding="utf-8"
        )
        config = config_module.load(project / "letterhead.yaml")
        return builder.build_all(config)[0].pdf.read_bytes()

    def claims(self, pdf, tag):
        """What the PDF's own metadata says it conforms to.

        Asserted on rather than the exit code, and rather than the version in
        the first line. A compile that succeeded proves Typst found nothing to
        object to; what a reader at the other end goes by is the identification
        written into the file, and that is a different thing to have got right.
        """
        return re.findall(rf"{tag}>([^<]+)<".encode(), pdf)

    @pytest.mark.parametrize(
        "standard, part, level",
        [("a-2b", "2", "B"), ("a-3b", "3", "B"), ("a-2u", "2", "U"), ("a-3u", "3", "U")],
    )
    def test_the_archival_standards_identify_themselves(
        self, project, standard, part, level
    ):
        pdf = self.build(project, standard)
        assert pdf.startswith(b"%PDF-1.7")
        assert self.claims(pdf, "pdfaid:part") == [part.encode()]
        assert self.claims(pdf, "pdfaid:conformance") == [level.encode()]
        # PDF/A embeds the colour space the page is to be read in; without one
        # the file identifies as something it is not.
        assert b"/OutputIntent" in pdf

    @pytest.mark.parametrize("standard", ["a-4", "a-4f", "a-4e"])
    def test_pdf_a_4_is_the_pdf_2_0_edition(self, project, standard):
        pdf = self.build(project, standard)
        assert pdf.startswith(b"%PDF-2.0")
        assert self.claims(pdf, "pdfaid:part") == [b"4"]

    @needs_alt_text
    def test_ua_1_needs_no_edit_to_the_scaffold(self, project):
        # The band is drawn as a page artifact and PDF/UA-1 allows no link in
        # one, so `resolve` drops the targets; the scaffold's own drawings
        # carry the descriptions it wants. Both of those are the release, and
        # this is the test that says so.
        pdf = self.build(project, "ua-1")
        assert self.claims(pdf, "pdfuaid:part") == [b"1"]
        # Tagged, and marked as tagged: the structure a screen reader follows
        # instead of guessing the reading order from where the ink sits.
        assert b"/StructTreeRoot" in pdf and b"/MarkInfo" in pdf

    @needs_alt_text
    def test_archival_and_accessible_together(self, project):
        pdf = self.build(project, "[a-3b, ua-1]")
        assert self.claims(pdf, "pdfaid:part") == [b"3"]
        assert self.claims(pdf, "pdfuaid:part") == [b"1"]

    def test_nothing_asked_for_still_writes_an_ordinary_pdf(self, project):
        config = config_module.load(project / "letterhead.yaml")
        pdf = builder.build_all(config)[0].pdf.read_bytes()
        assert pdf.startswith(b"%PDF")
        assert self.claims(pdf, "pdfaid:part") == []

    @needs_alt_text
    def test_a_pair_typst_cannot_satisfy_says_where_it_was_asked_for(self, project):
        # PDF/A-4 is PDF 2.0 and PDF/UA-1 is not. Typst explains that far
        # better than a table kept here would; what it cannot say is that the
        # request came out of a file, so that much is added.
        with pytest.raises(BuildError) as caught:
            self.build(project, "[a-4, ua-1]")
        assert "PDF/A-4" in caught.value.message
        assert "pdf.standard" in caught.value.hint

    @needs_alt_text
    def test_a_picture_with_no_description_is_named(self, project):
        letter = project / "example-letter.md"
        text = letter.read_text(encoding="utf-8")
        start = text.index("![A plan of the roof")
        end = text.index("](assets/plate-roof-plan.svg)")
        letter.write_text(text[:start] + "![" + text[end:], encoding="utf-8")

        with pytest.raises(BuildError) as caught:
            self.build(project, "ua-1")
        # Typst says "missing alt text" and names no picture, which in a
        # document carrying three of them is the start of a search.
        assert "plate-roof-plan.svg" in caught.value.hint
        assert "plate-collection-point.svg" not in caught.value.hint

    def test_the_footer_keeps_its_links_without_ua_1(self, project):
        config = config_module.load(project / "letterhead.yaml")
        resolved = config_module.resolve(
            config, Document.load(project / "example-letter.md"), "en"
        )
        rows = [row for column in resolved["footer"]["columns"] for row in column["rows"]]
        assert any(row["link"] for row in rows), "the scaffold no longer links anything"


class TestFindingUndescribedPictures:
    """Which pictures carry no description, read off the generated Typst.

    Asked only once Typst has refused a document for want of alt text, so what
    matters is that the names it produces are right — a picture wrongly listed
    here would send somebody looking at a file that is fine.
    """

    def test_a_described_picture_is_not_listed(self):
        source = '#box(image("images/plate.svg", width: 48.0%, alt: "A plate"))\n'
        assert builder._undescribed_pictures(source) == []

    def test_an_undescribed_one_is(self):
        source = '#box(image("images/plate.svg", width: 48.0%))\n'
        assert builder._undescribed_pictures(source) == ["images/plate.svg"]

    def test_a_description_may_close_a_bracket_it_did_not_open(self):
        # Which is why the call is scanned rather than matched: "(2000 l)" ends
        # the argument list as far as any pattern counting brackets can tell,
        # and the `alt:` before it would then belong to nothing.
        source = '#box(image("images/tank.svg", alt: "The tank (2000 l), full"))\n'
        assert builder._undescribed_pictures(source) == []

    def test_a_description_may_contain_a_quotation_mark(self):
        source = '#box(image("images/sign.svg", alt: "The sign reads \\"stop\\""))\n'
        assert builder._undescribed_pictures(source) == []

    def test_each_picture_is_judged_on_its_own(self):
        source = (
            '#box(image("images/a.svg", alt: "A"))\n'
            '#box(image("images/b.svg"))\n'
            '#figure(image("images/c.svg", width: 82.0%, alt: "C"),\n'
            "  caption: [A caption])\n"
            '#box(image("images/d.svg", width: 20.0%))\n'
        )
        assert builder._undescribed_pictures(source) == ["images/b.svg", "images/d.svg"]

    def test_the_same_picture_twice_is_named_once(self):
        source = '#box(image("images/a.svg"))\n#box(image("images/a.svg"))\n'
        assert builder._undescribed_pictures(source) == ["images/a.svg"]


class TestAltTextSupport:
    """The one thing about a standard that can be settled without compiling."""

    def _pandoc(self, monkeypatch, version):
        monkeypatch.setattr(
            toolchain, "find", lambda name: toolchain.Tool(name, "/pandoc", version)
        )

    def test_an_archival_standard_does_not_need_it(self, monkeypatch):
        self._pandoc(monkeypatch, "3.1")
        builder.require_alt_text_support(["a-2b", "a-3b", "a-4"])

    def test_nothing_asked_for_needs_nothing(self, monkeypatch):
        self._pandoc(monkeypatch, "3.1")
        builder.require_alt_text_support([])

    def test_ua_1_on_an_old_pandoc_is_refused_by_name(self, monkeypatch):
        self._pandoc(monkeypatch, "3.1")
        with pytest.raises(ConfigError, match="pdf.standard") as caught:
            builder.require_alt_text_support(["ua-1"])
        # Both versions, because the sentence has to say what to do about it.
        assert "3.1" in caught.value.message
        assert toolchain.PANDOC_ALT_TEXT in caught.value.hint

    def test_the_accessible_levels_of_pdf_a_are_refused_too(self, monkeypatch):
        self._pandoc(monkeypatch, "3.1")
        with pytest.raises(ConfigError) as caught:
            builder.require_alt_text_support(["a-2a"])
        assert "a-2a" in caught.value.message

    def test_a_pandoc_that_carries_it_passes(self, monkeypatch):
        self._pandoc(monkeypatch, "3.9.0.1")
        builder.require_alt_text_support(["ua-1", "a-3a"])

    def test_a_pandoc_that_is_not_there_is_not_this_error(self, monkeypatch):
        # Reported as a missing program, once, by the section above it.
        monkeypatch.setattr(
            toolchain, "find", lambda name: toolchain.Tool(name, None, None)
        )
        builder.require_alt_text_support(["ua-1"])


class TestStagingImages:
    """The pictures a document names, copied in and repointed.

    These work on the Typst that Pandoc would have written, so they need
    neither Pandoc nor Typst to run.
    """

    def stage(self, project, typst_source, workdir=None):
        workdir = workdir or (project / "build")
        workdir.mkdir(exist_ok=True)
        generated = workdir / "document.typ"
        generated.write_text(typst_source, encoding="utf-8")
        staged = builder._stage_images(project, workdir, generated)
        return staged, generated.read_text(encoding="utf-8")

    def test_a_picture_is_copied_in_and_the_call_repointed(self, project):
        staged, rewritten = self.stage(
            project, '#figure(image("assets/plate-condition.svg", alt: "A plate"))\n'
        )
        assert staged == ["images/plate-condition.svg"]
        assert 'image("images/plate-condition.svg"' in rewritten
        assert (project / "build" / "images" / "plate-condition.svg").is_file()

    def test_the_same_picture_twice_is_copied_once(self, project):
        staged, rewritten = self.stage(
            project,
            '#box(image("assets/logo.svg"))\n#box(image("./assets/logo.svg"))\n',
        )
        assert staged == ["images/logo.svg"]
        assert rewritten.count('image("images/logo.svg")') == 2

    def test_two_pictures_of_the_same_name_are_kept_apart(self, project):
        (project / "one").mkdir()
        (project / "two").mkdir()
        for folder in ("one", "two"):
            shutil.copy2(SCAFFOLD / "logo.svg", project / folder / "mark.svg")
        staged, rewritten = self.stage(
            project, '#box(image("one/mark.svg"))\n#box(image("two/mark.svg"))\n'
        )
        assert staged == ["images/mark-2.svg", "images/mark.svg"]
        assert 'image("images/mark-2.svg")' in rewritten

    def test_a_name_typst_would_stumble_over_is_made_plain(self, project):
        shutil.copy2(SCAFFOLD / "logo.svg", project / "a mark (final).svg")
        staged, _ = self.stage(project, '#box(image("a mark (final).svg"))\n')
        assert staged == ["images/a-mark-final-.svg"]

    def test_a_document_with_no_pictures_is_left_alone(self, project):
        source = "#box[nothing to place]\n"
        staged, rewritten = self.stage(project, source)
        assert staged == []
        assert rewritten == source

    def test_a_missing_picture_says_where_it_was_looked_for(self, project):
        with pytest.raises(BuildError) as caught:
            self.stage(project, '#box(image("assets/nowhere.png"))\n')
        assert "nowhere.png" in caught.value.message
        assert str(project) in caught.value.hint

    def test_a_remote_picture_is_refused(self, project):
        # Typst places files and fetches nothing, and a build that reached out
        # to the network would be a different tool.
        with pytest.raises(BuildError, match="fetches nothing"):
            self.stage(project, '#box(image("https://example.com/plate.png"))\n')

    def test_a_format_typst_cannot_place_is_refused(self, project):
        (project / "plate.pdf").write_bytes(b"%PDF-1.4")
        with pytest.raises(BuildError, match="cannot place"):
            self.stage(project, '#box(image("plate.pdf"))\n')


class TestStaging:
    def config(self, project):
        return config_module.load(project / "letterhead.yaml")

    def test_a_missing_logo_points_at_the_configuration(self, project):
        (project / "assets" / "logo.svg").unlink()
        with pytest.raises(ConfigError) as caught:
            builder._stage_logo(self.config(project), project, "assets/logo.svg")
        assert "letterhead.yaml" in caught.value.hint

    def test_a_logo_typst_cannot_place_is_refused_up_front(self, project):
        (project / "assets" / "logo.pdf").write_bytes(b"%PDF-1.4")
        with pytest.raises(ConfigError, match="cannot place"):
            builder._stage_logo(self.config(project), project, "assets/logo.pdf")

    def test_a_missing_background_names_its_own_setting(self, project):
        with pytest.raises(ConfigError) as caught:
            builder._stage_background(self.config(project), project, "assets/sheet.png")
        assert "page.background.image" in caught.value.message

    def test_a_background_exported_as_pdf_is_refused_with_the_reason(self, project):
        # The mistake this feature invites: a designer exports the sheet from
        # InDesign the way they always do, and Typst places no PDF.
        (project / "assets" / "sheet.pdf").write_bytes(b"%PDF-1.4")
        with pytest.raises(ConfigError) as caught:
            builder._stage_background(self.config(project), project, "assets/sheet.pdf")
        assert "cannot place" in caught.value.message
        assert "raster" in caught.value.hint

    def test_a_staged_asset_keeps_its_format_and_takes_the_given_name(self, project):
        config = self.config(project)
        staged = builder._stage_background(config, project, "assets/logo.svg")
        assert staged == "background.svg"
        assert (project / "background.svg").is_file()

    def test_an_asset_that_is_not_named_stages_nothing(self, project):
        assert builder._stage_background(self.config(project), project, None) is None

    def test_a_font_path_that_is_not_a_directory_is_refused(self, project):
        # Written into the `fonts:` the scaffold already has, rather than
        # appended as a second one: a file that sets the same key twice is now
        # refused before anything in it is read.
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        lines = text.splitlines(True)
        at = next(i for i, line in enumerate(lines) if line.startswith("fonts:"))
        lines.insert(at + 1, "  paths: [assets/logo.svg]\n")
        (project / "letterhead.yaml").write_text("".join(lines), encoding="utf-8")
        config = config_module.load(project / "letterhead.yaml")
        with pytest.raises(ConfigError, match="not a directory"):
            builder.font_paths(config)


@needs_toolchain
class TestProfilesEndToEnd:
    """A profile, all the way to the file on the disk.

    Asserted on the PDF's own identification rather than on the bytes
    differing: two builds of the same source differ anyway, because the
    creation timestamp is in there.
    """

    def with_profile(self, project):
        path = project / "letterhead.yaml"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nprofiles:\n  archival:\n    pdf:\n      standard: a-3b\n",
            encoding="utf-8",
        )
        return path

    def test_nothing_asked_for_builds_what_it_always_did(self, project):
        path = self.with_profile(project)
        assert cli.main(["build", "-c", str(path)]) == 0
        assert b"pdfaid:part" not in (project / "example-letter.pdf").read_bytes()

    def test_the_flag_reaches_the_compiler(self, project):
        path = self.with_profile(project)
        assert cli.main(["build", "-c", str(path), "--profile", "archival"]) == 0
        assert b"pdfaid:part>3<" in (project / "example-letter.pdf").read_bytes()

    def test_a_document_may_ask_for_one_itself(self, project):
        path = self.with_profile(project)
        letter = project / "example-letter.md"
        letter.write_text(
            letter.read_text(encoding="utf-8").replace(
                "---\n", "---\nprofile: archival\n", 1
            ),
            encoding="utf-8",
        )
        assert cli.main(["build", "-c", str(path)]) == 0
        assert b"pdfaid:part>3<" in (project / "example-letter.pdf").read_bytes()

    def test_an_unknown_profile_stops_the_run(self, project):
        path = self.with_profile(project)
        assert cli.main(["build", "-c", str(path), "--profile", "archivl"]) == 1

    def test_a_front_matter_block_prints(self, project):
        letter = project / "example-letter.md"
        letter.write_text(
            letter.read_text(encoding="utf-8").replace(
                "---\n", "---\nletterhead:\n  header:\n    show: false\n", 1
            ),
            encoding="utf-8",
        )
        config = config_module.load(project / "letterhead.yaml")
        assert builder.build_all(config)[0].pdf.read_bytes().startswith(b"%PDF")


class TestTheBuildDirectoryIsNotASource:
    """Nothing the build writes is something the build reads.

    `builder`'s own module docstring says so; `discover` did not know it. The
    reachable version needed a recursive `documents.include` and a build
    directory that had survived — which is either `--keep-build`, or any failed
    build, since the staging is only cleared on success.
    """

    def recursive(self, project):
        path = project / "letterhead.yaml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                '  include: ["*.md"]', '  include: ["**/*.md"]'
            ),
            encoding="utf-8",
        )
        assert '**/*.md' in path.read_text(encoding="utf-8")
        return config_module.load(path)

    def leave_intermediates(self, config, slug="example-letter"):
        """What a failed build, or `--keep-build`, leaves on the disk."""
        workdir = config.build_dir / slug
        workdir.mkdir(parents=True)
        (workdir / "body.prep.md").write_text("= Left over\n", encoding="utf-8")
        return workdir / "body.prep.md"

    def test_an_intermediate_is_not_discovered(self, project):
        config = self.recursive(project)
        left = self.leave_intermediates(config)
        assert left.is_file()
        assert [path.name for path in builder.discover_documents(config)] == [
            "example-letter.md"
        ]

    def test_it_is_not_watched_either(self, project):
        # Three commands, one answer: a watch that disagreed would rebuild on
        # its own staging and never settle.
        config = self.recursive(project)
        left = self.leave_intermediates(config)
        assert left not in cli._watched(config, None, [])

    @needs_toolchain
    def test_check_and_build_agree_after_a_failure(self, project):
        # The shape the defect actually took: a document with a mistake in it
        # fails, leaving its staging behind; the mistake is then fixed, and the
        # next build reported the *old* error out of the build directory.
        (project / "broken.md").write_text(
            "# Broken\n\n![a plate](missing.svg)\n", encoding="utf-8"
        )
        config = self.recursive(project)
        with pytest.raises(BuildError, match="no such picture"):
            builder.build_all(config)
        assert (config.build_dir / "broken" / "body.prep.md").is_file()

        (project / "broken.md").write_text("# Broken\n\nNo picture.\n", encoding="utf-8")
        results = builder.build_all(config)
        assert sorted(result.pdf.name for result in results) == [
            "broken.pdf",
            "example-letter.pdf",
        ]

    @needs_toolchain
    def test_keep_build_can_be_run_twice(self, project):
        config = self.recursive(project)
        builder.build_all(config, keep_build=True)
        again = builder.build_all(config, keep_build=True)
        assert [result.pdf.name for result in again] == ["example-letter.pdf"]


@needs_real_permissions
class TestAPlaceThatCannotBeWrittenNamesItsSetting:
    """Every other failure here arrives as a message; these used to arrive as a
    `PermissionError` several frames up a traceback, naming a directory the
    user never typed."""

    @pytest.fixture
    def locked(self, tmp_path):
        directory = tmp_path / "locked"
        directory.mkdir()
        directory.chmod(0o500)
        yield directory
        directory.chmod(0o700)

    def settings(self, project, **changes):
        path = project / "letterhead.yaml"
        text = path.read_text(encoding="utf-8")
        for old, new in changes.items():
            assert old in text, old
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        return config_module.load(path)

    def test_a_build_directory_that_cannot_be_made(self, project, locked):
        config = self.settings(
            project, **{"build_dir: .letterhead-build": f"build_dir: {locked}/build"}
        )
        with pytest.raises(BuildError) as caught:
            builder.build_all(config)
        assert caught.value.message.startswith("build_dir:")
        assert "Permission denied" in caught.value.message
        assert "'build_dir'" in caught.value.hint

    @needs_toolchain
    def test_an_output_directory_that_cannot_be_made(self, project, locked):
        config = self.settings(project, **{"  output: .": f"  output: {locked}/out"})
        with pytest.raises(BuildError) as caught:
            builder.build_all(config)
        assert caught.value.message.startswith("documents.output:")
        assert "'documents.output'" in caught.value.hint

    def test_the_command_reports_it_rather_than_raising(self, project, locked, capsys):
        self.settings(
            project, **{"build_dir: .letterhead-build": f"build_dir: {locked}/build"}
        )
        assert cli.main(["build", "-c", str(project / "letterhead.yaml")]) == 1
        assert "build_dir:" in capsys.readouterr().err

    def test_a_logo_that_cannot_be_read_names_the_logo(self, project):
        # Not the build directory. A copy has two ends, and the setting is the
        # name that is right whichever end of it failed.
        logo = project / "assets" / "logo.svg"
        logo.chmod(0o000)
        try:
            config = config_module.load(project / "letterhead.yaml")
            with pytest.raises(BuildError, match="^brand.logo:"):
                builder.build_all(config)
        finally:
            logo.chmod(0o644)

    @needs_toolchain
    def test_a_picture_that_cannot_be_read_names_the_picture(self, project):
        plate = project / "assets" / "plate-condition.svg"
        plate.chmod(0o000)
        try:
            config = config_module.load(project / "letterhead.yaml")
            with pytest.raises(BuildError) as caught:
                builder.build_all(config)
            # Spelled as the document wrote it, like `no such picture` beside it,
            # and without the absolute path repeating the same name.
            assert caught.value.message.startswith("assets/plate-condition.svg: ")
            assert str(plate) not in caught.value.message
        finally:
            plate.chmod(0o644)
