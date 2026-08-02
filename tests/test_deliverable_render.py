"""Tests for the menteapex-deliverable renderer (scripts/render.py).

The renderer is deterministic: Markdown template (source of truth) → on-brand HTML.
These tests pin the pure transforms — comment stripping, placeholder detection,
the Markdown subset our Legal/ templates use, and the brand-book-first token wiring.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# render.py lives beside the skill, not in the repo-level scripts/ dir.
_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills" / "menteapex-deliverable" / "scripts"
)
sys.path.insert(0, str(_SKILL_SCRIPTS))

import render  # noqa: E402


class TestStripComments:
    def test_removes_html_comment_guidance_block(self):
        md = "Before\n<!-- guidance the author must not ship -->\nAfter"
        assert render.strip_comments(md) == "Before\n\nAfter"

    def test_removes_multiline_comment(self):
        md = "# Title\n<!--\nmulti\nline\n-->\nBody"
        assert "multi" not in render.strip_comments(md)
        assert "# Title" in render.strip_comments(md)
        assert "Body" in render.strip_comments(md)


class TestFindPlaceholders:
    def test_finds_bracketed_prose_slot(self):
        md = "**For:** [Client / business]\n**Date:** [date]"
        assert render.find_placeholders(md) == ["[Client / business]", "[date]"]

    def test_markdown_link_is_not_a_placeholder(self):
        md = "See [the registry](../clients.md) for details."
        assert render.find_placeholders(md) == []

    def test_reference_style_link_label_is_not_a_placeholder(self):
        # A bracketed slot immediately followed by ( is a link, not a fill-in.
        md = "Price is [€Y] per the [offer](offer.md)."
        assert render.find_placeholders(md) == ["[€Y]"]


class TestMarkdownToHtml:
    def test_headings_h1_to_h4(self):
        html = render.markdown_to_html("# One\n## Two\n### Three\n#### Four")
        assert "<h1>One</h1>" in html
        assert "<h2>Two</h2>" in html
        assert "<h3>Three</h3>" in html
        assert "<h4>Four</h4>" in html

    def test_bold_and_italic_inline(self):
        html = render.markdown_to_html("A **bold** and *italic* word.")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_inline_link(self):
        html = render.markdown_to_html("See [our site](https://menteapex.com).")
        assert '<a href="https://menteapex.com">our site</a>' in html

    def test_unordered_list(self):
        html = render.markdown_to_html("- first\n- second\n- third")
        assert "<ul>" in html and "</ul>" in html
        assert html.count("<li>") == 3
        assert "<li>first</li>" in html

    def test_ordered_list(self):
        html = render.markdown_to_html("1. alpha\n2. beta")
        assert "<ol>" in html and "</ol>" in html
        assert "<li>alpha</li>" in html and "<li>beta</li>" in html

    def test_horizontal_rule(self):
        html = render.markdown_to_html("Above\n\n---\n\nBelow")
        assert "<hr" in html

    def test_blockquote(self):
        html = render.markdown_to_html("> a quiet aside")
        assert "<blockquote>" in html
        assert "a quiet aside" in html

    def test_paragraph_wrapping(self):
        html = render.markdown_to_html("First para.\n\nSecond para.")
        assert "<p>First para.</p>" in html
        assert "<p>Second para.</p>" in html

    def test_pipe_table_renders_with_header(self):
        md = "| Item | Price |\n|---|---|\n| Full value | €X |\n| **Your price** | **€Y** |"
        html = render.markdown_to_html(md)
        assert "<table>" in html and "</table>" in html
        assert "<thead>" in html
        assert "<th>Item</th>" in html and "<th>Price</th>" in html
        assert "<td>Full value</td>" in html
        # inline formatting still applies inside cells
        assert "<strong>Your price</strong>" in html

    def test_html_is_escaped_in_text(self):
        html = render.markdown_to_html("5 < 6 & 7 > 4")
        assert "&lt;" in html and "&amp;" in html and "&gt;" in html


def _brand(tmp_path):
    """A minimal Brand/ source: brand-book.html + tokens/tokens.css."""
    brand = tmp_path / "Brand"
    (brand / "tokens").mkdir(parents=True)
    (brand / "brand-book.html").write_text("<html>brand</html>")
    (brand / "tokens" / "tokens.css").write_text(":root{--abyssal-navy:#0B1E3F;}")
    return brand


class TestBrandFreshness:
    def test_not_stale_when_tokens_newer_than_book(self, tmp_path):
        brand = _brand(tmp_path)
        import os
        import time

        now = time.time()
        os.utime(brand / "brand-book.html", (now - 100, now - 100))
        os.utime(brand / "tokens" / "tokens.css", (now, now))
        assert render.brand_is_stale(brand) is False

    def test_stale_when_book_newer_than_tokens(self, tmp_path):
        brand = _brand(tmp_path)
        import os
        import time

        now = time.time()
        os.utime(brand / "tokens" / "tokens.css", (now - 100, now - 100))
        os.utime(brand / "brand-book.html", (now, now))
        assert render.brand_is_stale(brand) is True

    def test_resolve_brand_reads_live_tokens_css(self, tmp_path):
        brand = _brand(tmp_path)
        resolved = render.resolve_brand(brand)
        assert "--abyssal-navy:#0B1E3F" in resolved.tokens_css
        assert resolved.source == brand

    def test_resolve_brand_missing_source_falls_back_with_warning(self, tmp_path):
        missing = tmp_path / "nope"
        fallback = tmp_path / "vendored"
        fallback.mkdir()
        (fallback / "tokens.css").write_text(":root{--fallback:1;}")
        resolved = render.resolve_brand(missing, fallback_dir=fallback)
        assert "--fallback:1" in resolved.tokens_css
        assert resolved.warning  # a non-empty warning string

    def test_check_returns_unfilled_placeholders(self):
        md = "**For:** [Client]\nDate: [date]\nDone."
        assert render.check(md) == ["[Client]", "[date]"]

    def test_check_ignores_placeholders_inside_comments(self):
        md = "<!-- guidance: put [the client] here -->\n**For:** Acme Ltd"
        assert render.check(md) == []


class TestBuildDocument:
    def _brand(self):
        return render.ResolvedBrand(
            tokens_css=":root{--abyssal-navy:#0B1E3F;--mediterranean-gold:#C9A84C;}",
            fonts_css="/* fonts */",
            wordmark_svg="<svg id='wm'></svg>",
            source=None,
        )

    def test_embeds_live_tokens_and_body(self):
        html = render.build_document(
            "# Your offer\n\nA clear outcome.",
            self._brand(),
            kind="letterhead",
            lang="en",
        )
        assert "--abyssal-navy:#0B1E3F" in html  # live tokens inlined
        assert "<h1>Your offer</h1>" in html
        assert "A clear outcome." in html

    def test_sets_language_attribute(self):
        html = render.build_document(
            "Hola", self._brand(), kind="letterhead", lang="es-ES"
        )
        assert '<html lang="es-ES"' in html

    def test_identity_kind_includes_masthead_with_wordmark(self):
        html = render.build_document(
            "# Proposal", self._brand(), kind="identity", lang="en", title="Proposal"
        )
        assert '<section class="masthead">' in html
        assert "<svg id='wm'></svg>" in html  # wordmark opens the document

    def test_letterhead_kind_has_no_full_bleed_masthead(self):
        html = render.build_document(
            "# Invoice", self._brand(), kind="letterhead", lang="en"
        )
        assert (
            '<section class="masthead">' not in html
        )  # element, not the CSS class def

    def test_multipage_flow_css_present(self):
        html = render.build_document(
            "Body", self._brand(), kind="letterhead", lang="en"
        )
        # the brand book's Multi-page Documents law, encoded as print CSS
        assert "orphans: 2" in html and "widows: 2" in html
        assert "break-inside: avoid" in html
        assert "table-header-group" in html


class TestCheckCli:
    def test_check_exits_1_and_lists_when_placeholders_remain(self, tmp_path, capsys):
        doc = tmp_path / "offer.md"
        doc.write_text("**For:** [Client / business]\nDate: [date]")
        code = render.main([str(doc), "--check"])
        assert code == 1
        assert "[Client / business]" in capsys.readouterr().out

    def test_check_exits_0_when_fully_filled(self, tmp_path, capsys):
        doc = tmp_path / "offer.md"
        doc.write_text("**For:** Acme Ltd\nDate: 2026-07-21")
        assert render.main([str(doc), "--check"]) == 0


class TestFootnoteMarkersAreNotPlaceholders:
    # A numeric bracket is a footnote marker only when the DOCUMENT DEFINES it.
    # Excluding every numeric bracket instead meant `[15] days` in the
    # engagement agreement and `[30] days` in the DPA — real value slots, in
    # documents with no reference list at all — passed the completeness gate,
    # and both shipped to clients with visible brackets where a number belonged.
    # These tests were originally written against `handover`, whose markers
    # genuinely are footnotes; the rule they pinned was wrong for the others.

    REFERENCE_LIST = (
        "\n\n**Technical reference**\n\n"
        "- [1] Hosting account: Cloudflare\n"
        "- [2] Domain: Cloudflare Registrar\n"
        "- [10] Storage: R2\n"
    )

    def test_a_defined_marker_is_not_a_slot(self):
        md = "See the schedule [1] and the annex [2]." + self.REFERENCE_LIST
        assert render.find_placeholders(md) == []

    def test_a_multi_digit_defined_marker_is_not_a_slot(self):
        assert (
            render.find_placeholders("As noted [10] above." + self.REFERENCE_LIST) == []
        )

    def test_prose_slot_alongside_a_defined_marker_is_still_flagged(self):
        md = "**For:** [Client / business] — see clause [1]." + self.REFERENCE_LIST
        assert render.find_placeholders(md) == ["[Client / business]"]

    def test_currency_slot_with_digits_still_flagged(self):
        # Only PURELY numeric brackets can ever be markers; [€Y] keeps its digit.
        assert render.find_placeholders("Price [€Y], value [€X].") == ["[€Y]", "[€X]"]

    def test_check_passes_on_a_document_whose_markers_are_defined(self):
        md = "All the prose is filled.\n\nReference [1] and note [2]." + (
            self.REFERENCE_LIST
        )
        assert render.check(md) == []

    def test_an_undefined_numeric_bracket_is_a_slot(self):
        """The correction. No reference list anywhere in the document, so
        `[30]` is a number somebody forgot to fill in."""
        md = "Delete or return all personal data within [30] days."
        assert render.find_placeholders(md) == ["[30]"]

    def test_the_engagement_agreements_payment_term_is_flagged(self):
        md = "Invoices are due within [15] days of issue."
        assert render.find_placeholders(md) == ["[15]"]

    def test_defined_footnotes_are_read_from_the_reference_list(self):
        assert render.defined_footnotes(self.REFERENCE_LIST) == {"1", "2", "10"}


class TestFileUrl:
    # Headless Chrome needs an absolute file:// URI. A relative --out path produced a
    # malformed URL (`file://out/x.html` → host "out") that baked an error page into
    # the PDF. Always resolve to an absolute, percent-encoded file URI.
    def test_relative_path_becomes_absolute_file_uri(self):
        url = render._file_url(Path("out/deliverable.html"))
        assert url.startswith("file:///")
        assert url.endswith("/out/deliverable.html")

    def test_absolute_path_preserved(self, tmp_path):
        target = tmp_path / "x.html"
        assert render._file_url(target) == target.resolve().as_uri()

    def test_spaces_are_percent_encoded(self, tmp_path):
        target = tmp_path / "my doc.html"
        url = render._file_url(target)
        assert " " not in url
        assert "my%20doc.html" in url


class TestPdfSuccessMeansChromeSucceeded:
    """`html_to_pdf` declared success from "a non-empty file exists at the
    output path". With a PDF already there from an earlier render, a Chrome
    that died left the OLD file in place, non-empty, and this returned True --
    so the operator was told the render succeeded and emailed yesterday's
    price.
    """

    @staticmethod
    def _fake_chrome(monkeypatch, returncode, *, writes=None):
        monkeypatch.setattr(render, "_find_chrome", lambda: "/fake/chrome")

        def fake_run(argv, check, capture_output, timeout):
            if writes is not None:
                Path(writes).write_bytes(b"%PDF-1.4 FRESH")
            return subprocess.CompletedProcess(argv, returncode, b"", b"boom")

        monkeypatch.setattr(render.subprocess, "run", fake_run)

    def test_a_failed_chrome_does_not_report_success(self, tmp_path, monkeypatch):
        pdf = tmp_path / "offer.pdf"
        pdf.write_bytes(b"%PDF-1.4 STALE - PRICE 5000 EUR")
        self._fake_chrome(monkeypatch, returncode=1)

        assert render.html_to_pdf(tmp_path / "offer.html", pdf) is False

    def test_a_failed_chrome_leaves_no_stale_pdf_to_be_mistaken_for_the_result(
        self, tmp_path, monkeypatch
    ):
        pdf = tmp_path / "offer.pdf"
        pdf.write_bytes(b"%PDF-1.4 STALE - PRICE 5000 EUR")
        self._fake_chrome(monkeypatch, returncode=1)

        render.html_to_pdf(tmp_path / "offer.html", pdf)

        assert not pdf.exists()

    def test_a_successful_chrome_still_reports_success(self, tmp_path, monkeypatch):
        """The control: refusing a stale result must not refuse a real one."""
        pdf = tmp_path / "offer.pdf"
        self._fake_chrome(monkeypatch, returncode=0, writes=pdf)

        assert render.html_to_pdf(tmp_path / "offer.html", pdf) is True
        assert pdf.read_bytes() == b"%PDF-1.4 FRESH"

    def test_a_zero_exit_that_wrote_nothing_is_not_success(self, tmp_path, monkeypatch):
        pdf = tmp_path / "offer.pdf"
        self._fake_chrome(monkeypatch, returncode=0)

        assert render.html_to_pdf(tmp_path / "offer.html", pdf) is False

    def test_a_hung_chrome_is_bounded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render, "_find_chrome", lambda: "/fake/chrome")

        def fake_run(argv, check, capture_output, timeout):
            raise subprocess.TimeoutExpired(argv, timeout)

        monkeypatch.setattr(render.subprocess, "run", fake_run)

        assert render.html_to_pdf(tmp_path / "x.html", tmp_path / "x.pdf") is False


class TestTheMastheadIsReachableAndNeverHollow:
    def test_the_kicker_and_meta_reach_the_cover_page_through_the_cli(
        self, tmp_path, monkeypatch
    ):
        """Through `main`, not `build_document`. `build_document` always
        accepted `meta` and `doc_kicker`; the defect was that NOTHING passed
        them, so every `--kind identity` cover shipped with an empty kicker
        and an empty meta block. A test calling `build_document` directly
        passes with the defect fully present."""
        source = tmp_path / "offer.md"
        source.write_text("Body.", encoding="utf-8")
        monkeypatch.setattr(render, "html_to_pdf", lambda html_path, pdf_path: False)

        render.main(
            [
                str(source),
                "--kind",
                "identity",
                "--title",
                "Website build",
                "--kicker",
                "PROPOSAL",
                "--meta",
                "Client=Acme",
                "--meta",
                "Date=2026-08-02",
            ]
        )

        html = (tmp_path / "offer.html").read_text(encoding="utf-8")
        assert ">PROPOSAL<" in html
        assert "Acme" in html
        assert "2026-08-02" in html

    def test_an_empty_meta_block_is_omitted_not_rendered_hollow(self):
        """`.mh-meta` carries a border-top, so an empty one shipped a stray
        hairline rule with nothing under it on a client-facing navy cover."""
        html = render.build_document(
            "Body.",
            render.resolve_brand(Path("/nonexistent"), fallback_dir=render._ASSETS_DIR),
            kind="identity",
            lang="en",
            title="Website build",
        )

        assert 'class="mh-meta"' not in html
        assert 'class="doc"' not in html

    def test_meta_arguments_parse_into_ordered_cells(self):
        assert render._parse_meta(["Client=Acme", "Date=2026-08-02"]) == {
            "Client": "Acme",
            "Date": "2026-08-02",
        }

    def test_a_malformed_meta_argument_is_refused_not_dropped(self):
        with pytest.raises(ValueError, match="LABEL=VALUE"):
            render._parse_meta(["ClientAcme"])


class TestTheLanguageCodeIsValidated:
    def test_an_unknown_language_is_rejected(self, tmp_path):
        source = tmp_path / "doc.md"
        source.write_text("Body.", encoding="utf-8")

        with pytest.raises(SystemExit):
            render.main([str(source), "--lang", "xx-BAD"])

    def test_every_supported_language_is_accepted(self, tmp_path):
        source = tmp_path / "doc.md"
        source.write_text("Body.", encoding="utf-8")

        for language in render.SUPPORTED_LANGUAGES:
            render.main([str(source), "--lang", language, "--check"])


class TestAQuoteInAUrlCannotBreakOutOfTheAttribute:
    def test_the_href_is_quote_escaped(self):
        html = render._inline('[site](https://x.com/?a=1&b=2" onmouseover="x)')

        # The attribute value must contain no raw `"`, so nothing after the
        # injected quote can become an attribute of its own.
        href_value = html.split('href="', 1)[1].split('"', 1)[0]
        assert "&quot;" in href_value
        assert "onmouseover" in href_value  # inert: still inside the attribute

    def test_an_ordinary_link_is_unchanged(self):
        assert render._inline("[site](https://x.com/)") == (
            '<a href="https://x.com/">site</a>'
        )

    def test_an_ampersand_in_a_query_string_is_escaped_exactly_once(self):
        """A second full `html.escape` on the href would make the `&amp;` from
        the body pass into `&amp;amp;`, rendering a literal `&amp;` in the URL."""
        html = render._inline("[q](https://x.com/?a=1&b=2)")

        assert 'href="https://x.com/?a=1&amp;b=2"' in html

    def test_a_quote_in_body_prose_is_not_escaped(self):
        """`quote=False` on body text is deliberate — escaping every quote in
        prose would litter the document with `&quot;`."""
        assert '"' in render._inline('He said "hello".')
