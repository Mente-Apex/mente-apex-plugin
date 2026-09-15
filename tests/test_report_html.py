"""The shared HTML report renderer (issue #130).

`gof` was the only lens with an HTML path, and it was 114 lines of styling prose
an agent re-executed with a Write call every run. The issue's point is that the
current state is the only one that cannot be right: either HTML belongs to all
six lenses and the umbrella, or it belongs to none.

It now lives once, as code -- which is also what makes these tests possible. A
prose spec is a guard nothing can check.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from report_html import (
    GRADE_BADGES,
    TIER_BADGES,
    BadgeRule,
    badge_for,
    document_title,
    parse_report,
    render_html,
)

SAMPLE = """# SOLID Report — 2026-09-15

Preamble line.

## Summary

Two findings.

## [solid/Critical-1] OrderService does too much

- **Location:** `orders.py:42`
- **Reader impact:** three reasons to change

```python
class OrderService:  # <- the angle bracket must survive
    pass
```

## [solid/Minor-2] Rename `tmp`

| Field | Value |
|---|---|
| Risk | Low |
"""


class TestStructure:
    def test_each_heading_becomes_its_own_section(self):
        sections = parse_report(SAMPLE)

        titles = [section.title for section in sections]
        assert "Summary" in titles
        assert "[solid/Critical-1] OrderService does too much" in titles

    def test_the_document_title_names_the_page_not_a_card(self):
        """`# SOLID Report` is the page; making it a card would put the whole
        report inside its own first section."""
        assert document_title(SAMPLE) == "SOLID Report — 2026-09-15"
        assert "SOLID Report — 2026-09-15" not in [
            section.title for section in parse_report(SAMPLE)
        ]

    def test_anchors_are_derived_from_titles_so_they_are_stable(self):
        """Counted anchors change when a section is inserted above, which
        breaks every link anyone saved."""
        first = parse_report(SAMPLE)
        second = parse_report(SAMPLE)

        assert [section.anchor for section in first] == [
            section.anchor for section in second
        ]
        assert all(" " not in section.anchor for section in first)


class TestBadgesAreDataNotCode:
    def test_a_tier_heading_earns_its_tier_badge(self):
        rule = badge_for("[solid/Critical-1] OrderService does too much", TIER_BADGES)

        assert rule is not None and rule.label == "Critical"

    def test_a_grade_heading_earns_its_grade_badge(self):
        rule = badge_for("Singleton — C — Structural issues", GRADE_BADGES)

        assert rule is not None and rule.label == "C"

    def test_the_first_matching_rule_wins_so_order_is_precedence(self):
        rules = (
            BadgeRule(r"Critical", "Specific", "#000000"),
            BadgeRule(r".", "Catch-all", "#ffffff"),
        )

        assert badge_for("Critical thing", rules).label == "Specific"

    def test_a_lens_with_a_new_vocabulary_needs_no_edit_here(self):
        """The OCP seam: a rule list is passed in, so a seventh lens badging
        something else is a new list, not a change to the renderer."""
        acceptance = (BadgeRule(r"\bLeakage\b", "Leakage", "#a855f7"),)

        assert badge_for("Scenario Leakage in checkout.feature", acceptance).label == (
            "Leakage"
        )

    def test_an_unbadged_heading_renders_without_one(self):
        assert badge_for("Coverage & method", TIER_BADGES) is None


class TestTheRenderedPage:
    def test_it_is_self_contained(self):
        """No CDN, no external stylesheet, no remote font or image: the artifact
        has to open from a file:// path with no server."""
        page = render_html(SAMPLE)

        assert "<style>" in page
        assert "http://" not in page and "https://" not in page
        assert "cdn" not in page.lower()

    def test_source_code_in_the_report_cannot_close_the_document(self):
        """A report quotes code. An unescaped `<` ends the markup and the rest
        of the page silently disappears."""
        page = render_html(SAMPLE)

        assert "&lt;- the angle bracket must survive" in page
        assert "<- the angle bracket must survive" not in page

    def test_every_section_gets_a_card_and_a_nav_link(self):
        page = render_html(SAMPLE)

        for anchor in ("summary", "solid-critical-1-orderservice-does-too-much"):
            assert f'id="{anchor}"' in page
            assert f'href="#{anchor}"' in page

    def test_a_tier_badge_is_painted_on_the_finding(self):
        page = render_html(SAMPLE, badges=TIER_BADGES)

        assert 'class="badge"' in page and "Critical" in page

    def test_fenced_code_survives_as_a_pre_block(self):
        page = render_html(SAMPLE)

        assert "<pre><code>" in page

    def test_a_table_renders_as_a_table_without_its_separator_row(self):
        page = render_html(SAMPLE)

        assert "<table>" in page
        assert "|---|" not in page

    def test_it_works_in_both_colour_schemes(self):
        """Every other artifact this plugin writes is read in a terminal; this
        one is read in a browser that may be in either mode."""
        page = render_html(SAMPLE)

        assert "prefers-color-scheme: dark" in page

    def test_an_empty_report_still_renders_a_page(self):
        page = render_html("")

        assert page.startswith("<!doctype html>")


class TestTheCli:
    @staticmethod
    def run_cli(*arguments):
        return subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts" / "report_html.py"),
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_it_writes_beside_the_report_by_default(self, tmp_path):
        report = tmp_path / "SOLID-REPORT-2026-09-15.md"
        report.write_text(SAMPLE, encoding="utf-8")

        completed = self.run_cli(str(report))

        assert completed.returncode == 0, completed.stderr
        assert (tmp_path / "SOLID-REPORT-2026-09-15.html").is_file()

    def test_a_missing_report_is_an_error_not_a_traceback(self, tmp_path):
        completed = self.run_cli(str(tmp_path / "nope.md"))

        assert completed.returncode == 2
        assert "Traceback" not in completed.stderr

    @pytest.mark.parametrize("vocabulary", ["tier", "grade", "both"])
    def test_every_badge_vocabulary_is_selectable(self, tmp_path, vocabulary):
        report = tmp_path / "REPORT.md"
        report.write_text(SAMPLE, encoding="utf-8")

        completed = self.run_cli(str(report), "--badges", vocabulary)

        assert completed.returncode == 0, completed.stderr
