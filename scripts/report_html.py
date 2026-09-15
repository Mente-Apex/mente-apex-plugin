"""One HTML renderer for every lens's report (issue #130).

`gof` was the only lens shipping an HTML path, as `references/html-report.md` --
114 lines of styling prose an agent re-executed with a Write call on every run.
That is the state the issue calls the only one that cannot be right: either HTML
is worth having, in which case it belongs to all six lenses and the umbrella, or
it is not, in which case one lens carries a maintenance surface nobody else has.

It is worth having, so it lives here once, as code. Three things follow from
that which prose could not give:

- **A template change is one edit, not N.** The section->card mapping is coupled
  to the report template's shape; when the tiered container was renamed
  `## Recommendations` -> `## Findings`, a per-lens spec had to be chased.
- **It is testable.** A prose spec is a guard nothing can check -- an agent
  either followed it or did not, and the only reviewer is a human looking at a
  browser.
- **It costs no model time.** Rendering is deterministic work that was being
  paid for in tokens once per report.

**Vocabulary is data, not code.** Lenses badge different things: `gof` grades
patterns A-F, everyone else tiers findings Critical/Major/Minor. Those are
`BadgeRule` lists passed in, so a lens with a new vocabulary is a new rule list
and not an edit to this module.

**Self-contained, always.** Inline CSS, no CDN, no external font, no remote
image, no required JavaScript -- the artifact has to open from a file:// path in
any browser with no server, which is the whole reason it is a single file.
"""

import argparse
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
FENCE = re.compile(r"^\s*```")
# The explicit anchor every lens report-template mandates above each finding
# heading, e.g. `<a id="solid-critical-1"></a>`. Deliberately strict: an id of
# word characters and hyphens only, nothing else allowed through, because this is
# the one place raw markup from the report reaches the page unescaped.
EXPLICIT_ANCHOR = re.compile(r'^\s*<a\s+id="([\w-]+)"\s*>\s*</a>\s*$')
INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass(frozen=True)
class BadgeRule:
    """One badge a heading can earn: a pattern to look for and how to paint it.

    `pattern` is matched against the heading text. The first rule that matches
    wins, so a caller orders its rules from most to least specific.
    """

    pattern: str
    label: str
    background: str
    foreground: str = "#ffffff"

    def matches(self, heading_text):
        return re.search(self.pattern, heading_text) is not None


# Critical/Major/Minor: the tiering every lens but `gof` uses.
TIER_BADGES = (
    BadgeRule(r"\bCritical\b", "Critical", "#dc2626"),
    BadgeRule(r"\bMajor\b", "Major", "#f59e0b"),
    BadgeRule(r"\bMinor\b", "Minor", "#3b82f6"),
)

# A-F pattern grades, `gof`'s vocabulary, kept because it is a real distinction
# that lens makes and not one to flatten into the tier scale.
GRADE_BADGES = (
    BadgeRule(r"\bA\b\s*—|\bA —", "A", "#22c55e"),
    BadgeRule(r"\bB\b\s*—|\bB —", "B", "#3b82f6"),
    BadgeRule(r"\bC\b\s*—|\bC —", "C", "#f59e0b"),
    BadgeRule(r"\bD\b\s*—|\bD —", "D", "#f97316"),
    BadgeRule(r"\bF\b\s*—|\bF —", "F", "#dc2626"),
)

DEFAULT_BADGES = GRADE_BADGES + TIER_BADGES


@dataclass
class Section:
    """One `##`-or-deeper heading and the lines beneath it."""

    level: int
    title: str
    body: list = field(default_factory=list)
    explicit_anchor: str = ""

    @property
    def is_internal(self):
        """True for a section that must not be published — see
        `INTERNAL_SECTIONS`."""
        return self.title.strip().lower() in INTERNAL_SECTIONS

    @property
    def anchor(self):
        """A URL-safe id for the sidebar link.

        **The report's own explicit anchor wins.** Every lens template mandates
        `<a id="<lens>-<tier>-<n>"></a>` above each finding heading, and the
        umbrella's *Full detail* links point at exactly that — so deriving an id
        from the title instead left every one of those links dead, and made the
        id change whenever a finding was retitled.

        The derived slug is the fallback for a section with no anchor of its own
        (Summary, Coverage & method). Derived from the title rather than counted,
        so two runs of the same report produce the same ids.
        """
        if self.explicit_anchor:
            return self.explicit_anchor
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return slug or "section"


def parse_report(markdown_text):
    """Split a report into its sections. Preamble lands in a lead section.

    Only structure -- no styling decisions here, so the same parse feeds any
    renderer a later caller writes.
    """
    sections = []
    current = Section(level=2, title="Report", body=[])
    inside_fence = False
    pending_anchor = ""
    for line in markdown_text.splitlines():
        if FENCE.match(line):
            inside_fence = not inside_fence
            current.body.append(line)
            continue
        if inside_fence:
            # A `##` line inside a fence is QUOTED EVIDENCE, not a heading.
            # Treating it as one invented a phantom section and its nav link, and
            # tore the fence into two unbalanced blocks across two cards -- and
            # these lenses audit Markdown-heavy trees where quoting a heading is
            # the ordinary case.
            current.body.append(line)
            continue
        anchor_match = EXPLICIT_ANCHOR.match(line)
        if anchor_match:
            # Held for the heading it precedes, and never emitted as body: it was
            # being html-escaped into visible junk text while the id it declares
            # went missing, so every Findings-index deep link resolved nowhere.
            pending_anchor = anchor_match.group(1)
            continue
        match = HEADING.match(line)
        if match and len(match.group(1)) == 1:
            # The document title. It names the page, not a card.
            current.body.append(line)
            continue
        if match:
            if current.body or current.title != "Report":
                sections.append(current)
            current = Section(
                level=len(match.group(1)),
                title=match.group(2).strip(),
                explicit_anchor=pending_anchor,
            )
            pending_anchor = ""
            continue
        current.body.append(line)
    sections.append(current)
    return [section for section in sections if section.title or any(section.body)]


def badge_for(heading_text, rules):
    """The first rule that matches, or None. Order encodes precedence."""
    for rule in rules:
        if rule.matches(heading_text):
            return rule
    return None


def document_title(markdown_text, fallback="Report"):
    for line in markdown_text.splitlines():
        match = HEADING.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return fallback


def _inline(text):
    """Escape, then re-apply the inline marks we support.

    Escaping first is not a detail: a report quotes source code, and an
    unescaped `<` closes the document's own markup. Everything below operates on
    already-escaped text.
    """
    escaped = html.escape(text)
    escaped = INLINE_CODE.sub(r"<code>\1</code>", escaped)
    escaped = BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = LINK.sub(r'<a href="\2">\1</a>', escaped)
    return escaped


def _render_body(lines):
    """Markdown body -> HTML, for the subset a lens report actually uses.

    Deliberately not a Markdown implementation: fenced code, lists, tables and
    paragraphs are what the report template emits, and a general parser here
    would be a dependency and a second thing to keep correct.
    """
    parts = []
    in_code = False
    in_list = False
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                parts.append("</code></pre>")
            else:
                parts.append("<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            parts.append(html.escape(line))
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= set("-: ") for cell in cells):
                continue  # the |---|---| separator row
            if not in_table:
                parts.append("<table>")
                in_table = True
            row = "".join(f"<td>{_inline(cell)}</td>" for cell in cells)
            parts.append(f"<tr>{row}</tr>")
            continue
        if in_table:
            parts.append("</table>")
            in_table = False
        if stripped.startswith(("- ", "* ")):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline(stripped[2:])}</li>")
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        if stripped:
            parts.append(f"<p>{_inline(stripped)}</p>")
    if in_code:
        parts.append("</code></pre>")
    if in_list:
        parts.append("</ul>")
    if in_table:
        parts.append("</table>")
    return "\n".join(parts)


# Sections internal to the Markdown workflow, never rendered. The Markdown report
# is gitignored; the HTML is the artifact that gets forwarded to a colleague or a
# client. `Reviewer notes` carries every finding the critic PRUNED with the reason
# it was pruned, and `Apply log` carries timestamps and diffstats -- neither is
# for an outside reader, and the HTML is a read-only preview rather than a place
# a finding's Status gets edited. The rule came from gof's per-lens spec and was
# lost when the renderer was shared; it lives in code now, where it is checkable.
INTERNAL_SECTIONS = frozenset({"reviewer notes", "apply log"})

STYLE = """
:root { color-scheme: light dark; --bg:#ffffff; --fg:#1f2328; --muted:#57606a;
  --line:#d0d7de; --card:#f6f8fa; --side:#1f2328; --sidefg:#e6edf3; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1117; --fg:#e6edf3;
  --muted:#9198a1; --line:#30363d; --card:#161b22; --side:#010409; --sidefg:#e6edf3; } }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.65 system-ui,
  -apple-system, "Segoe UI", sans-serif; }
header { position:sticky; top:0; z-index:2; background:var(--bg);
  border-bottom:1px solid var(--line); padding:14px 24px; }
header h1 { margin:0; font-size:18px; }
header .meta { color:var(--muted); font-size:13px; }
.layout { display:flex; gap:0; align-items:flex-start; }
nav { position:sticky; top:64px; flex:0 0 250px; background:var(--side);
  color:var(--sidefg); min-height:calc(100vh - 64px); padding:18px 14px; }
nav a { display:block; color:var(--sidefg); opacity:.78; text-decoration:none;
  padding:5px 8px; border-radius:6px; font-size:13px; }
nav a:hover, nav a.active { opacity:1; background:rgba(255,255,255,.10); }
main { flex:1 1 auto; max-width:900px; padding:28px 32px; }
section { border:1px solid var(--line); background:var(--card); border-radius:10px;
  padding:16px 20px; margin:0 0 18px; }
section h2, section h3, section h4 { margin-top:0; }
code { background:rgba(127,127,127,.16); padding:1px 5px; border-radius:4px;
  font:13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
pre { background:rgba(127,127,127,.12); padding:12px 14px; border-radius:8px;
  overflow-x:auto; }
pre code { background:none; padding:0; }
table { border-collapse:collapse; width:100%; overflow-x:auto; display:block; }
td { border:1px solid var(--line); padding:6px 10px; font-size:14px; }
.badge { display:inline-block; padding:1px 9px; border-radius:999px; font-size:12px;
  font-weight:600; margin-right:8px; vertical-align:middle; }
@media (max-width: 800px) { .layout { flex-direction:column; }
  nav { position:static; width:100%; min-height:0; flex-basis:auto; }
  main { padding:20px 16px; } }
"""

NAV_SCRIPT = """
const links = [...document.querySelectorAll('nav a')];
const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (!entry.isIntersecting) return;
    links.forEach((link) => link.classList.toggle(
      'active', link.getAttribute('href') === '#' + entry.target.id));
  });
}, { rootMargin: '-10% 0px -80% 0px' });
document.querySelectorAll('section[id]').forEach((s) => observer.observe(s));
"""


def render_html(markdown_text, *, title=None, subtitle="", badges=DEFAULT_BADGES):
    """A self-contained HTML page for one lens report.

    `badges` is the lens's vocabulary. `subtitle` is whatever the caller wants
    under the title -- ordinarily the generation date, which the Markdown report
    already carries in its filename.
    """
    sections = parse_report(markdown_text)
    page_title = title or document_title(markdown_text)

    nav_links = []
    cards = []
    used_anchors = {}
    for section in sections:
        if section.is_internal:
            continue
        rule = badge_for(section.title, badges)
        badge = (
            f'<span class="badge" style="background:{rule.background};'
            f'color:{rule.foreground}">{html.escape(rule.label)}</span>'
            if rule
            else ""
        )
        # Two lenses can both emit `### Critical`, and a duplicate id makes the
        # second one unreachable — the nav link scrolls to the first.
        anchor = section.anchor
        seen_count = used_anchors.get(anchor, 0)
        used_anchors[anchor] = seen_count + 1
        if seen_count:
            anchor = f"{anchor}-{seen_count + 1}"

        heading_level = min(max(section.level, 2), 4)
        cards.append(
            f'<section id="{anchor}">'
            f"<h{heading_level}>{badge}{_inline(section.title)}</h{heading_level}>"
            f"{_render_body(section.body)}"
            f"</section>"
        )
        nav_links.append(f'<a href="#{anchor}">{html.escape(section.title)}</a>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page_title)}</title>
<style>{STYLE}</style></head>
<body>
<header><h1>{html.escape(page_title)}</h1>
<div class="meta">{html.escape(subtitle)}</div></header>
<div class="layout">
<nav>{"".join(nav_links)}</nav>
<main>{"".join(cards)}</main>
</div>
<script>{NAV_SCRIPT}</script>
</body></html>
"""


BADGE_SETS = {"tier": TIER_BADGES, "grade": GRADE_BADGES, "both": DEFAULT_BADGES}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render a lens report as a self-contained HTML preview."
    )
    parser.add_argument("report", help="Path to the Markdown report.")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Where to write the HTML (default: the report path with .html).",
    )
    parser.add_argument(
        "--badges",
        choices=sorted(BADGE_SETS),
        default="both",
        help="Which vocabulary to badge: tier (Critical/Major/Minor), grade "
        "(A-F, gof), or both.",
    )
    parser.add_argument("--subtitle", default="")
    arguments = parser.parse_args(argv)

    source = Path(arguments.report)
    if not source.is_file():
        print(f"no such report: {source}", file=sys.stderr)
        return 2
    destination = (
        Path(arguments.output) if arguments.output else source.with_suffix(".html")
    )
    destination.write_text(
        render_html(
            source.read_text(encoding="utf-8"),
            subtitle=arguments.subtitle,
            badges=BADGE_SETS[arguments.badges],
        ),
        encoding="utf-8",
    )
    print(str(destination))
    return 0


if __name__ == "__main__":
    import report_html

    sys.exit(report_html.main())
