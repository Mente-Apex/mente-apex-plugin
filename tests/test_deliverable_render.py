"""Tests for the menteapex-deliverable renderer (scripts/render.py).

The renderer is deterministic: Markdown template (source of truth) → on-brand HTML.
These tests pin the pure transforms — comment stripping, placeholder detection,
the Markdown subset our Legal/ templates use, and the brand-book-first token wiring.
"""
import sys
from pathlib import Path

# render.py lives beside the skill, not in the repo-level scripts/ dir.
_SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "menteapex-deliverable" / "scripts"
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
        import os, time
        now = time.time()
        os.utime(brand / "brand-book.html", (now - 100, now - 100))
        os.utime(brand / "tokens" / "tokens.css", (now, now))
        assert render.brand_is_stale(brand) is False

    def test_stale_when_book_newer_than_tokens(self, tmp_path):
        brand = _brand(tmp_path)
        import os, time
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
            "# Your offer\n\nA clear outcome.", self._brand(), kind="letterhead", lang="en"
        )
        assert "--abyssal-navy:#0B1E3F" in html  # live tokens inlined
        assert "<h1>Your offer</h1>" in html
        assert "A clear outcome." in html

    def test_sets_language_attribute(self):
        html = render.build_document("Hola", self._brand(), kind="letterhead", lang="es-ES")
        assert '<html lang="es-ES"' in html

    def test_identity_kind_includes_masthead_with_wordmark(self):
        html = render.build_document(
            "# Proposal", self._brand(), kind="identity", lang="en", title="Proposal"
        )
        assert '<section class="masthead">' in html
        assert "<svg id='wm'></svg>" in html  # wordmark opens the document

    def test_letterhead_kind_has_no_full_bleed_masthead(self):
        html = render.build_document("# Invoice", self._brand(), kind="letterhead", lang="en")
        assert '<section class="masthead">' not in html  # element, not the CSS class def

    def test_multipage_flow_css_present(self):
        html = render.build_document("Body", self._brand(), kind="letterhead", lang="en")
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
