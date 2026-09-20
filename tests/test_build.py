"""End-to-end builds.

These run the real Pandoc and the real Typst, and are skipped when either is
missing, so a contributor without the toolchain can still run the rest.
"""

import json
import re
import shutil

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

    def test_archival_and_accessible_together(self, project):
        pdf = self.build(project, "[a-3b, ua-1]")
        assert self.claims(pdf, "pdfaid:part") == [b"3"]
        assert self.claims(pdf, "pdfuaid:part") == [b"1"]

    def test_nothing_asked_for_still_writes_an_ordinary_pdf(self, project):
        config = config_module.load(project / "letterhead.yaml")
        pdf = builder.build_all(config)[0].pdf.read_bytes()
        assert pdf.startswith(b"%PDF")
        assert self.claims(pdf, "pdfaid:part") == []

    def test_a_pair_typst_cannot_satisfy_says_where_it_was_asked_for(self, project):
        # PDF/A-4 is PDF 2.0 and PDF/UA-1 is not. Typst explains that far
        # better than a table kept here would; what it cannot say is that the
        # request came out of a file, so that much is added.
        with pytest.raises(BuildError) as caught:
            self.build(project, "[a-4, ua-1]")
        assert "PDF/A-4" in caught.value.message
        assert "pdf.standard" in caught.value.hint

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
