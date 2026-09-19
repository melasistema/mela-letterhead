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
    def test_a_missing_logo_points_at_the_configuration(self, project):
        (project / "assets" / "logo.svg").unlink()
        config = config_module.load(project / "letterhead.yaml")
        with pytest.raises(ConfigError) as caught:
            builder._stage_logo(config, project)
        assert "letterhead.yaml" in caught.value.hint

    def test_a_logo_typst_cannot_place_is_refused_up_front(self, project):
        (project / "assets" / "logo.pdf").write_bytes(b"%PDF-1.4")
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        (project / "letterhead.yaml").write_text(
            text.replace("logo: assets/logo.svg", "logo: assets/logo.pdf"), encoding="utf-8"
        )
        config = config_module.load(project / "letterhead.yaml")
        with pytest.raises(ConfigError, match="cannot place"):
            builder._stage_logo(config, project)

    def test_a_font_path_that_is_not_a_directory_is_refused(self, project):
        text = (project / "letterhead.yaml").read_text(encoding="utf-8")
        (project / "letterhead.yaml").write_text(
            text + "\nfonts:\n  paths: [assets/logo.svg]\n", encoding="utf-8"
        )
        config = config_module.load(project / "letterhead.yaml")
        with pytest.raises(ConfigError, match="not a directory"):
            builder.font_paths(config)
