"""End-to-end builds.

These run the real Pandoc and the real Typst, and are skipped when either is
missing, so a contributor without the toolchain can still run the rest.
"""

import json
import shutil

import pytest

from mela_letterhead import builder
from mela_letterhead import config as config_module
from mela_letterhead.builder import ASSETS
from mela_letterhead.errors import ConfigError

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
