"""End-to-end builds.

These run the real Pandoc and the real Typst, and are skipped when either is
missing, so a contributor without the toolchain can still run the rest.
"""

import json
import shutil

import pytest

from mela_letterhead import builder, cli
from mela_letterhead import config as config_module
from mela_letterhead.builder import ASSETS
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
