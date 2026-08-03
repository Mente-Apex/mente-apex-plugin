"""Contract tests for the six lens report templates and the code-quality
umbrella's consolidated template, against docs/report-contract.md (WS-9).

docs/report-contract.md is the single source of truth for the finding schema
(the ID scheme, the sanctioned lens prefixes, the canonical field set, the
alias table). These tests parse that doc as data rather than keeping a
second, hand-maintained copy that could quietly drift out of sync with it:
change the contract doc's alias table, sanctioned prefixes, or lens list, and
the expectations asserted here move with it automatically. The one exception
is the six-name canonical field list itself (Location, Evidence, Reader
impact, Proposed change, Risk, Status) -- report-contract.md states it inline
alongside the documented-optional `Related` field in unstructured prose, so
parsing it reliably would trade a small, stable, brief-enumerated constant
for a fragile prose scraper; it is pinned as a plain tuple instead.

Authored-prose guard, not runtime code: these tests assert that the six lens
templates (and the umbrella's) carry the sections/fields/wording the shared
refactor engine (docs/refactor-workflow.md) and the umbrella's dispatch and
linking depend on. Dependency-free on purpose, mirroring
tests/test_ddd_skill_structure.py and tests/test_code_quality_skill_structure.py.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_CONTRACT_PATH = REPO_ROOT / "docs" / "report-contract.md"
REFACTOR_WORKFLOW_PATH = REPO_ROOT / "docs" / "refactor-workflow.md"
CONSOLIDATED_TEMPLATE_PATH = (
    REPO_ROOT / "skills" / "code-quality" / "references" / "report-template.md"
)

# 9.2's floor: the six fields every finding must carry, per report-contract.md's
# "Canonical per-finding fields" section. `Related` is documented there as
# omittable ("a lens with nothing to cross-reference may omit the line"), so it
# is deliberately not part of this required set.
CANONICAL_FIELDS = (
    "Location",
    "Evidence",
    "Reader impact",
    "Proposed change",
    "Risk",
    "Status",
)
TIERS = ("critical", "major", "minor")


def read_text(path):
    """Read a repo file, failing the test with the path if it's missing."""
    assert path.is_file(), f"expected file missing: {path}"
    return path.read_text(encoding="utf-8")


def extract_section(text, heading_text):
    """Return the text between a Markdown heading containing heading_text and
    the next heading of the same-or-higher level (fewer or equal '#'s).

    Scopes a parse to one section of a doc instead of the whole file, so a
    marker that only happens to reappear in a later section can't paper over
    its absence from the section under test. Mirrors the helper already used
    by tests/test_code_quality_skill_structure.py, kept local here so this
    file carries no cross-test-module coupling.
    """
    heading_pattern = re.compile(
        r"^(#{1,6})\s.*" + re.escape(heading_text) + r".*$", re.MULTILINE
    )
    heading_match = heading_pattern.search(text)
    assert heading_match, f"heading containing {heading_text!r} not found"
    level = len(heading_match.group(1))
    section_start = heading_match.end()
    next_heading_pattern = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE)
    next_heading_match = next_heading_pattern.search(text, section_start)
    section_end = next_heading_match.start() if next_heading_match else len(text)
    return text[section_start:section_end]


def fenced_markdown_blocks(text):
    """Return the content of every ```markdown ... ``` fence in a reference
    doc -- the literal skeleton a reviewer copies verbatim into the real
    report. Prose around a fence (cross-links to shared docs, explanatory
    asides) is out of scope for fence-only guards like 9.3 and 9.6: it never
    ends up inside a generated report."""
    return re.findall(r"```markdown\n(.*?)\n```", text, re.DOTALL)


def parse_lens_directory_names(report_contract_text):
    """Read the per-lens rows of the Filename rule table as data: the set of
    lenses under test, derived from the contract doc instead of duplicated by
    hand. Excludes the umbrella's own 'code-quality (consolidated)' row."""
    section = extract_section(report_contract_text, "Filename rule")
    row_first_cells = re.findall(r"^\|\s*([a-z][a-z-]*)\s*\|", section, re.MULTILINE)
    return tuple(cell for cell in row_first_cells if cell != "code-quality")


def parse_id_scheme_prefixes(report_contract_text):
    """Read the '`<lens>` ∈ `...`' line of the ID scheme section as data --
    the sanctioned set of ID prefixes, parsed rather than duplicated."""
    section = extract_section(report_contract_text, "ID scheme")
    prefix_line_match = re.search(r"`<lens>` ∈ `([^`]+)`", section)
    assert prefix_line_match, "ID scheme section has no '<lens> ∈ ...' declaration"
    return tuple(prefix.strip() for prefix in prefix_line_match.group(1).split("|"))


def parse_declared_aliases(report_contract_text):
    """Parse the 'Alias table (D3)' into {(lens_name, canonical_field): [alias, ...]}
    for rows whose Treatment is 'Alias, kept'. A 'Renamed' row records a field
    name that used to exist and no longer lives in any template, so it grants
    no template an exemption from carrying the canonical name -- it is parsed
    but deliberately excluded from the returned alias map."""
    section = extract_section(report_contract_text, "Alias table (D3)")
    row_pattern = re.compile(
        r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*"
        r"\*\*(Alias, kept|Renamed)\*\*"
    )
    declared_aliases = {}
    for line in section.splitlines():
        row_match = row_pattern.match(line.strip())
        if not row_match:
            continue
        alias_name, lens_list, canonical_field, treatment = row_match.groups()
        if treatment != "Alias, kept":
            continue
        for lens_name in (
            raw_lens_name.strip() for raw_lens_name in lens_list.split(",")
        ):
            declared_aliases.setdefault((lens_name, canonical_field), []).append(
                alias_name
            )
    return declared_aliases


REPORT_CONTRACT_TEXT = read_text(REPORT_CONTRACT_PATH)
LENS_NAMES = parse_lens_directory_names(REPORT_CONTRACT_TEXT)
ID_SCHEME_PREFIXES = parse_id_scheme_prefixes(REPORT_CONTRACT_TEXT)
DECLARED_ALIASES = parse_declared_aliases(REPORT_CONTRACT_TEXT)


def lens_template_path(lens_name):
    return REPO_ROOT / "skills" / lens_name / "references" / "report-template.md"


def declared_id_prefix(lens_name):
    """Extract the lens's own declared ID prefix straight out of its
    template's prose, e.g. 'clean-arch' out of "Rec IDs are self-describing:
    `clean-arch/<tier>-<n>`" -- read from the template file rather than a
    lens-name -> prefix table hand-maintained here, since clean-architecture's
    directory name and ID prefix already differ and a second mapping is
    exactly the kind of duplicate that drifts."""
    template_text = read_text(lens_template_path(lens_name))
    prefix_match = re.search(
        r"Rec IDs are self-describing: `([a-z-]+)/<tier>-<n>`", template_text
    )
    assert prefix_match, f"{lens_name}: template does not declare its own ID prefix"
    return prefix_match.group(1)


def repo_markdown_files_under(*relative_directories):
    """Yield every .md file under the given repo-relative directories, minus
    the historical planning record (docs/superpowers/plans/, which
    deliberately quotes retired schemes it replaced) -- mirrors Task 2's
    sweep scope for the C*/M*/N* retirement."""
    for relative_directory in relative_directories:
        for markdown_path in (REPO_ROOT / relative_directory).rglob("*.md"):
            relative_posix = markdown_path.relative_to(REPO_ROOT).as_posix()
            if relative_posix.startswith("docs/superpowers/plans/"):
                continue
            yield markdown_path


# ---------------------------------------------------------------------------
# 9.1 -- ID scheme: <lens>/<tier>-<n> with the exact sanctioned prefixes, and
# no surviving mention of the retired C*/M*/N* scheme.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lens_name", LENS_NAMES)
def test_lens_declares_an_id_prefix_from_the_contracts_sanctioned_set(lens_name):
    """9.1: a lens template's own declared ID prefix must be a member of
    report-contract.md's sanctioned prefix set -- catches a template's prefix
    drifting (typo, rename) out of step with the contract that lists it."""
    prefix = declared_id_prefix(lens_name)
    assert prefix in ID_SCHEME_PREFIXES, (
        f"{lens_name}: declared ID prefix {prefix!r} is not in report-contract.md's "
        f"sanctioned set {ID_SCHEME_PREFIXES!r}"
    )


@pytest.mark.parametrize("lens_name", LENS_NAMES)
@pytest.mark.parametrize("tier", TIERS)
def test_lens_template_uses_the_lens_slash_tier_dash_n_id_scheme(lens_name, tier):
    """9.1: every tier's finding stub in the fenced skeleton carries an example
    ID of the shape <prefix>/<tier>-<n>, e.g. `[solid/major-1]` -- proves the
    scheme is actually laid down in the copy-paste skeleton, not just
    described in the surrounding prose."""
    prefix = declared_id_prefix(lens_name)
    fenced_text = "\n".join(
        fenced_markdown_blocks(read_text(lens_template_path(lens_name)))
    )
    assert re.search(
        rf"\[{re.escape(prefix)}/{tier}-\d+\]", fenced_text
    ), f"{lens_name}: fenced skeleton has no example [{prefix}/{tier}-<n>] finding id"


def test_no_file_outside_the_historical_plan_still_names_the_retired_c_m_n_scheme():
    """9.1: no shipped template or role doc under skills/ or docs/ (outside the
    historical planning record) mentions the retired C*/M*/N* ID scheme that
    <lens>/<tier>-<n> replaced -- docs/superpowers/plans/ is exempt because it
    deliberately quotes the scheme it replaced, mirroring Task 2's sweep."""
    offending_files = [
        str(markdown_path.relative_to(REPO_ROOT))
        for markdown_path in repo_markdown_files_under("skills", "docs")
        if "C*/M*/N*" in read_text(markdown_path)
    ]
    assert not offending_files, (
        f"retired C*/M*/N* ID scheme still mentioned outside "
        f"docs/superpowers/plans/: {offending_files}"
    )


# ---------------------------------------------------------------------------
# 9.2 -- canonical field set (or a declared alias) on every finding skeleton.
# ---------------------------------------------------------------------------


def extract_tier_stub(fenced_text, tier_label):
    """Return one tier's finding stub (e.g. 'Critical') from a fenced
    skeleton -- the text between '### <Tier>' and the next '### ' heading (or
    the end of the fence)."""
    stub_pattern = re.compile(
        rf"^### {tier_label}\n(.*?)(?=^### |\Z)", re.DOTALL | re.MULTILINE
    )
    stub_match = stub_pattern.search(fenced_text)
    assert stub_match, f"no {tier_label!r} tier stub found in fenced skeleton"
    return stub_match.group(1)


def field_labels_in(stub_text):
    """Return the bolded '- **Field:**' labels a finding stub declares."""
    return re.findall(r"^-\s+\*\*([^:*]+):\*\*", stub_text, re.MULTILINE)


@pytest.mark.parametrize("lens_name", LENS_NAMES)
def test_critical_stub_carries_every_canonical_field_or_its_declared_alias(
    lens_name,
):
    """9.2: each of the six canonical fields must appear on the lens's
    Critical finding stub, either under its canonical name or a declared
    alias from report-contract.md's Alias table -- an undeclared field name is
    "a defect, not a style choice" per that table's own rule."""
    fenced_text = "\n".join(
        fenced_markdown_blocks(read_text(lens_template_path(lens_name)))
    )
    stub_field_labels = set(field_labels_in(extract_tier_stub(fenced_text, "Critical")))
    missing_canonical_fields = [
        canonical_field
        for canonical_field in CANONICAL_FIELDS
        if canonical_field not in stub_field_labels
        and not set(DECLARED_ALIASES.get((lens_name, canonical_field), []))
        & stub_field_labels
    ]
    assert not missing_canonical_fields, (
        f"{lens_name}: Critical stub is missing canonical field(s) "
        f"{missing_canonical_fields} with no declared alias covering them "
        f"(report-contract.md Alias table); stub fields found: "
        f"{sorted(stub_field_labels)}"
    )


# ---------------------------------------------------------------------------
# 9.3 -- Apply log + Outcome inside the fenced skeleton; anchors on every tier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lens_name", LENS_NAMES)
def test_lens_template_fenced_skeleton_carries_apply_log_and_outcome_headings(
    lens_name,
):
    """9.3: every lens's fenced skeleton carries '## Apply log' and
    '## Outcome' -- including ddd and clean-code, whose own runs are
    analyze-only (never reach Phase 4-5): a finding either lens produces is
    still applicable once merged by the code-quality umbrella or opted into
    directly (docs/refactor-workflow.md's 'Status, Apply-log & Outcome
    format'), and needs headings to record that under."""
    fenced_text = "\n".join(
        fenced_markdown_blocks(read_text(lens_template_path(lens_name)))
    )
    assert (
        "## Apply log" in fenced_text
    ), f"{lens_name}: fenced skeleton missing '## Apply log'"
    assert (
        "## Outcome" in fenced_text
    ), f"{lens_name}: fenced skeleton missing '## Outcome'"


@pytest.mark.parametrize("lens_name", LENS_NAMES)
@pytest.mark.parametrize("tier", TIERS)
def test_anchor_precedes_every_tiers_finding_stub(lens_name, tier):
    """9.3: '<a id="<lens>-<tier>-<n>"></a>' precedes every tier's stub, not
    only Critical's -- markdown's auto-generated heading anchors can't handle
    the '/' in a rec id, so a Major/Minor umbrella 'Full detail' link would
    404 without an explicit anchor at that tier too."""
    prefix = declared_id_prefix(lens_name)
    fenced_text = "\n".join(
        fenced_markdown_blocks(read_text(lens_template_path(lens_name)))
    )
    assert re.search(rf'<a id="{re.escape(prefix)}-{tier}-\d+">', fenced_text), (
        f'{lens_name}: no <a id="{prefix}-{tier}-<n>"> anchor found for the '
        f"{tier} stub"
    )


# ---------------------------------------------------------------------------
# 9.4 -- D1's "own run" phrasing stays on one grep-safe line at every site.
# ---------------------------------------------------------------------------

D1_OWN_RUN_SITES = (
    REFACTOR_WORKFLOW_PATH,
    REPO_ROOT / "skills" / "ddd" / "SKILL.md",
    REPO_ROOT / "skills" / "clean-code" / "SKILL.md",
    REPO_ROOT / "skills" / "code-quality" / "references" / "report-template.md",
    lens_template_path("ddd"),
    lens_template_path("clean-code"),
)


@pytest.mark.parametrize(
    "site_path",
    D1_OWN_RUN_SITES,
    ids=[str(path.relative_to(REPO_ROOT)) for path in D1_OWN_RUN_SITES],
)
def test_own_run_phrasing_is_intact_and_grep_safe(site_path):
    """9.4: D1's decided formulation keeps the literal substring "own run"
    contiguous at every site stating the ddd/clean-code analyze-only
    carve-out -- guards against a markdown reflow silently re-splitting it
    across a line wrap ("own\\nrun"), which is exactly what defeated a plain
    grep before D1 and what motivated pinning it as one line."""
    assert "own run" in read_text(site_path), (
        f"{site_path.relative_to(REPO_ROOT)}: literal 'own run' substring not "
        "found -- D1's grep-safe phrasing regressed (split across a line wrap, "
        "reworded, or removed)"
    )


# ---------------------------------------------------------------------------
# 9.5 -- Phase-4 dispatch rule: lens-local implementer first, shared fallback.
# ---------------------------------------------------------------------------

DISPATCH_RULE_SITES = (
    REFACTOR_WORKFLOW_PATH,
    REPO_ROOT / "skills" / "code-quality" / "SKILL.md",
    lens_template_path("test-quality"),
)


@pytest.mark.parametrize(
    "site_path",
    DISPATCH_RULE_SITES,
    ids=[str(path.relative_to(REPO_ROOT)) for path in DISPATCH_RULE_SITES],
)
def test_phase_4_dispatch_rule_names_lens_local_implementer_first(site_path):
    """9.5: guards WS-2.1 -- every site stating the Phase-4 implementer
    dispatch rule must name both halves of it: try the lens's own
    agents/implementer.md first ("lens ships one"), fall back to the shared
    docs/refactor-agents/implementer.md only when it has none. A regression
    that silently drops either half would route a lens's recs (e.g.
    test-quality's mutation-gated ones) through the wrong implementer."""
    text = read_text(site_path)
    assert "lens ships one" in text, (
        f"{site_path.relative_to(REPO_ROOT)}: missing the lens-local-first half "
        "of the Phase-4 dispatch rule ('lens ships one')"
    )
    assert "docs/refactor-agents/implementer.md" in text, (
        f"{site_path.relative_to(REPO_ROOT)}: missing the shared-fallback half "
        "of the Phase-4 dispatch rule (docs/refactor-agents/implementer.md)"
    )


# ---------------------------------------------------------------------------
# 9.6 -- no stray relative link into the plugin repo inside a fenced skeleton.
# ---------------------------------------------------------------------------

# The umbrella's one sanctioned in-fence relative link: a report-to-report
# "Full detail" cross-reference, e.g. "../solid/SOLID-REPORT-<date>.md#...".
# It points at a sibling report file that lives in the SAME target repo's own
# docs/reports/ tree (the filename rule), so unlike "../../../docs/..." it is
# portable to any repo the skill runs in and is not "a link into the plugin
# repo" -- WS-1.7's actual guarded regression.
FULL_DETAIL_CROSS_REPORT_LINK = re.compile(
    r"^\.\./[a-z][a-z-]*/[A-Z][A-Z0-9-]*-REPORT-<date>\.md"
)


def relative_links_in(text):
    return re.findall(r"\]\((\.\./[^)]*)\)", text)


@pytest.mark.parametrize("lens_name_or_umbrella", (*LENS_NAMES, "code-quality"))
def test_fenced_skeleton_has_no_stray_relative_link_into_the_plugin_repo(
    lens_name_or_umbrella,
):
    """9.6: guards WS-1.7 -- a fenced report skeleton is copied verbatim into a
    generated report that can live in any target repo, so a link reaching
    "../../../docs/..." back into the plugin's own docs/ (e.g.
    status-vocabulary.md) would 404 there. WS-1.7 replaced those in-fence
    links with non-link mentions; only the umbrella's portable
    report-to-report "Full detail" link is exempt."""
    template_path = (
        CONSOLIDATED_TEMPLATE_PATH
        if lens_name_or_umbrella == "code-quality"
        else lens_template_path(lens_name_or_umbrella)
    )
    fenced_text = "\n".join(fenced_markdown_blocks(read_text(template_path)))
    stray_links = [
        link
        for link in relative_links_in(fenced_text)
        if not FULL_DETAIL_CROSS_REPORT_LINK.match(link)
    ]
    assert not stray_links, (
        f"{lens_name_or_umbrella}: fenced skeleton has stray relative link(s) "
        f"into the plugin repo: {stray_links}"
    )
