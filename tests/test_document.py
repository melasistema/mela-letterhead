import datetime

import pytest

from mela_letterhead.document import Document, discover, split_front_matter
from mela_letterhead.errors import DocumentError


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestFrontMatter:
    def test_splits_metadata_from_body(self):
        metadata, body = split_front_matter("---\ntitle: Offer\n---\n# Heading\n")
        assert metadata == {"title": "Offer"}
        assert body.strip() == "# Heading"

    def test_a_document_without_front_matter_is_all_body(self):
        metadata, body = split_front_matter("# Heading\n\nText.\n")
        assert metadata == {}
        assert body.startswith("# Heading")

    def test_a_rule_on_the_first_line_is_not_front_matter(self):
        # `---` opening a document is only front matter if it closes again.
        metadata, body = split_front_matter("---\n\nJust text.\n")
        assert metadata == {}

    def test_empty_front_matter(self):
        metadata, body = split_front_matter("---\n---\nText\n")
        assert metadata == {}

    def test_malformed_yaml_says_what_to_do(self):
        with pytest.raises(DocumentError) as caught:
            split_front_matter("---\ntitle: Offer: phase two\n---\nText\n")
        assert "quoted" in caught.value.hint

    def test_a_list_is_not_metadata(self):
        with pytest.raises(DocumentError, match="mapping"):
            split_front_matter("---\n- one\n- two\n---\nText\n")

    def test_a_key_set_twice_is_refused(self):
        with pytest.raises(DocumentError) as caught:
            split_front_matter("---\ntitle: Offer\nlang: it\ntitle: Quotation\n---\nText\n")
        assert "sets 'title' twice" in caught.value.message

    def test_the_lines_are_counted_from_the_top_of_the_file(self):
        # The front matter is parsed on its own and numbered from one again;
        # the person reading the error is looking at the whole file, where the
        # opening `---` is line one.
        with pytest.raises(DocumentError) as caught:
            split_front_matter("---\ntitle: Offer\nlang: it\ntitle: Quotation\n---\nText\n")
        assert "line 2" in caught.value.message
        assert "line 4" in caught.value.message


class TestTitles:
    def test_front_matter_wins(self, tmp_path):
        path = write(tmp_path, "d.md", "---\ntitle: From metadata\n---\n# From heading\n")
        assert Document.load(path).title == "From metadata"

    def test_falls_back_to_the_first_heading(self, tmp_path):
        path = write(tmp_path, "d.md", "Intro text\n\n## From heading\n")
        assert Document.load(path).title == "From heading"

    def test_heading_markup_is_stripped(self, tmp_path):
        path = write(tmp_path, "d.md", "# A *quoted* `offer`\n")
        assert Document.load(path).title == "A quoted offer"

    def test_falls_back_to_the_filename(self, tmp_path):
        path = write(tmp_path, "quarterly-report.md", "Just text.\n")
        assert Document.load(path).title == "quarterly-report"

    def test_running_title_defaults_to_the_title(self, tmp_path):
        path = write(tmp_path, "d.md", "---\ntitle: Long title\n---\nText\n")
        assert Document.load(path).running_title == "Long title"

    def test_running_title_can_differ(self, tmp_path):
        path = write(
            tmp_path, "d.md", "---\ntitle: Long title\nrunning-title: Short\n---\nText\n"
        )
        assert Document.load(path).running_title == "Short"


class TestFields:
    def test_reads_an_arbitrary_key(self, tmp_path):
        path = write(tmp_path, "d.md", "---\nreference: AQ-0184\n---\nText\n")
        assert Document.load(path).field("reference") == "AQ-0184"

    def test_missing_key_is_none(self, tmp_path):
        path = write(tmp_path, "d.md", "---\ntitle: x\n---\nText\n")
        assert Document.load(path).field("reference") is None

    def test_kebab_and_snake_case_are_the_same_key(self, tmp_path):
        path = write(tmp_path, "d.md", "---\nvalid-until: March\n---\nText\n")
        document = Document.load(path)
        assert document.field("valid_until") == "March"
        assert document.field("valid-until") == "March"

    def test_an_unquoted_date_is_formatted_not_stringified(self, tmp_path):
        # YAML reads `2026-09-14` as a date object; str() would print an ISO
        # date on paper that asks for 14.09.2026.
        path = write(tmp_path, "d.md", "---\ndate: 2026-09-14\n---\nText\n")
        assert Document.load(path, "%d.%m.%Y").field("date") == "14.09.2026"
        assert isinstance(Document.load(path).metadata["date"], datetime.date)

    def test_a_quoted_date_is_left_exactly_as_written(self, tmp_path):
        path = write(tmp_path, "d.md", '---\ndate: "14 settembre 2026"\n---\nText\n')
        assert Document.load(path, "%d.%m.%Y").field("date") == "14 settembre 2026"

    def test_a_blank_value_is_none(self, tmp_path):
        # An empty field becomes a line to fill in by hand, not the string "".
        path = write(tmp_path, "d.md", '---\nreference: "  "\n---\nText\n')
        assert Document.load(path).field("reference") is None

    def test_a_list_is_joined(self, tmp_path):
        path = write(tmp_path, "d.md", "---\ntags: [one, two]\n---\nText\n")
        assert Document.load(path).field("tags") == "one, two"


class TestOutputName:
    def test_defaults_to_the_source_name(self, tmp_path):
        path = write(tmp_path, "offer.md", "Text\n")
        assert Document.load(path).output_name == "offer"

    def test_front_matter_can_rename_it(self, tmp_path):
        path = write(tmp_path, "offer.md", "---\noutput: offer-2026.pdf\n---\nText\n")
        assert Document.load(path).output_name == "offer-2026"


class TestLoad:
    def test_missing_file(self, tmp_path):
        with pytest.raises(DocumentError, match="no such file"):
            Document.load(tmp_path / "absent.md")

    def test_non_utf8_file(self, tmp_path):
        path = tmp_path / "d.md"
        path.write_bytes(b"\xff\xfe# Heading")
        with pytest.raises(DocumentError, match="UTF-8"):
            Document.load(path)


class TestDiscover:
    def test_finds_markdown_and_honours_exclusions(self, tmp_path):
        for name in ("a.md", "b.md", "README.md", "notes.txt"):
            write(tmp_path, name, "Text\n")
        found = discover(tmp_path, ["*.md"], ["README.md"])
        assert [path.name for path in found] == ["a.md", "b.md"]

    def test_patterns_may_address_a_subdirectory(self, tmp_path):
        (tmp_path / "offers").mkdir()
        write(tmp_path, "offers/one.md", "Text\n")
        write(tmp_path, "top.md", "Text\n")
        found = discover(tmp_path, ["offers/*.md"], [])
        assert [path.name for path in found] == ["one.md"]

    def test_missing_directory(self, tmp_path):
        with pytest.raises(DocumentError, match="no such directory"):
            discover(tmp_path / "absent", ["*.md"], [])


class TestDiscoverSkipsTheBuildDirectory:
    """What a build leaves behind is not something to build.

    A build stages each document's rewritten Markdown as `body.prep.md` and
    removes it only on success, so a failed build — or `--keep-build` — leaves
    one where a recursive pattern will find it.
    """

    def test_a_recursive_pattern_does_not_find_intermediates(self, tmp_path):
        write(tmp_path, "letter.md", "Text\n")
        (tmp_path / ".letterhead-build" / "letter").mkdir(parents=True)
        write(tmp_path, ".letterhead-build/letter/body.prep.md", "Text\n")

        found = discover(tmp_path, ["**/*.md"], [], skip=tmp_path / ".letterhead-build")
        assert [path.name for path in found] == ["letter.md"]

    def test_without_the_skip_it_finds_them_all(self, tmp_path):
        """The defect this closes, kept as the reason the argument exists."""
        write(tmp_path, "letter.md", "Text\n")
        (tmp_path / ".letterhead-build" / "letter").mkdir(parents=True)
        write(tmp_path, ".letterhead-build/letter/body.prep.md", "Text\n")

        found = discover(tmp_path, ["**/*.md"], [])
        assert [path.name for path in found] == ["body.prep.md", "letter.md"]

    def test_a_build_directory_that_is_not_there_yet_is_no_trouble(self, tmp_path):
        write(tmp_path, "letter.md", "Text\n")
        found = discover(tmp_path, ["*.md"], [], skip=tmp_path / "never-built")
        assert [path.name for path in found] == ["letter.md"]

    def test_a_build_directory_outside_the_sources_skips_nothing(self, tmp_path):
        source = tmp_path / "project"
        source.mkdir()
        write(source, "letter.md", "Text\n")
        found = discover(source, ["*.md"], [], skip=tmp_path / "elsewhere")
        assert [path.name for path in found] == ["letter.md"]

    def test_a_build_directory_holding_the_sources_is_ignored(self, tmp_path):
        """`build_dir: .` is a misconfiguration, not an instruction to find
        nothing. The patterns win, and the build reports what they find."""
        write(tmp_path, "letter.md", "Text\n")
        found = discover(tmp_path, ["*.md"], [], skip=tmp_path)
        assert [path.name for path in found] == ["letter.md"]
