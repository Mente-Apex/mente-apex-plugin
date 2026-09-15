"""Structural guard for the `ddd` skill.

The `ddd` skill is authored prose, not runtime code, so its "tests" assert that
each file exists and carries the sections/fields the orchestration and the
plugin loader depend on. Dependency-free on purpose: PyYAML is not installed, so
frontmatter is parsed with string ops only (same discipline as
test_skill_shell_safety.py).
"""

import json
import re
from pathlib import Path

from skill_version_policy import assert_version_at_least

REPO_ROOT = Path(__file__).resolve().parents[1]
DDD_SKILL_DIR = REPO_ROOT / "skills" / "ddd"


def read_skill_file(relative_path):
    """Read a file under skills/ddd/, returning its text (fails the test if absent)."""
    target = DDD_SKILL_DIR / relative_path
    assert target.is_file(), f"expected skill file missing: {target}"
    return target.read_text(encoding="utf-8")


def parse_frontmatter(text):
    """Parse leading --- frontmatter into {key: value, '_body': rest}. No PyYAML."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "file does not start with a --- frontmatter block"
    raw_frontmatter, body = match.group(1), match.group(2)
    fields = {"_body": body}
    for line in raw_frontmatter.splitlines():
        key_value = re.match(r"^([A-Za-z0-9_-]+):\s?(.*)$", line)
        if key_value:
            fields[key_value.group(1)] = key_value.group(2)
    return fields


def test_skill_md_frontmatter_is_well_formed():
    fields = parse_frontmatter(read_skill_file("SKILL.md"))
    assert fields.get("name") == "ddd"
    assert fields.get("user-invocable") == "true"
    # description is a block scalar; the key line is `description: >` or `>-`
    assert "description" in fields
    # version lives under metadata: — floor, not equality, so a routine bump does
    # not break a guard that has nothing to say about the bump.
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert_version_at_least(frontmatter_text, (0, 1, 0))


def test_skill_md_covers_both_modes_and_both_gates():
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    required_markers = [
        "design",  # design mode
        "analyze",  # analyze mode
        "MODELING GATE",  # design-mode hard gate
        "MODEL REVIEW GATE",  # analyze-mode keep/discard gate
        "docs/domain",  # durable model artifacts
        "docs/reports/ddd",  # analyze report dir
        "programmatic",  # tdd handoff contract
    ]
    missing = [marker for marker in required_markers if marker not in body]
    assert not missing, f"SKILL.md missing required content: {missing}"


def test_analyze_mode_links_shared_workflow_instead_of_restating_it():
    """WS-5 (5.1/5.2/5.3/5.4): analyze mode must link docs/refactor-workflow.md
    like every other refactor lens, not restate its phases in ddd's own prose —
    and the report-dir exclusion goes through .git/info/exclude (a "no code
    changes" mode must not edit a committed .gitignore)."""
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    assert (
        "docs/refactor-workflow.md" in body
    ), "analyze mode must link the shared workflow rather than restate it"
    assert (
        "docs/lens-overlap.md" in body
    ), "the reviewer must be pointed at the lens-overlap hub, not just the SOLID cross-ref"
    assert (
        "clean-architecture" in body
    ), "lens-overlap cross-ref must reach the clean-architecture carve, not just SOLID"
    assert (
        ".gitignore" not in body
    ), "report-dir exclusion must use .git/info/exclude, never a committed .gitignore edit"
    assert ".git/info/exclude" in body


def test_reviewer_role_file_itself_points_at_lens_overlap():
    """The reviewer subagent only reliably sees what its own role file tells it
    to read — SKILL.md's orchestrator prose isn't enough, since ddd ships its
    own complete reviewer role with no shared docs/refactor-agents/reviewer.md
    fallback. Pin the cross-reference (both SOLID and the clean-architecture
    carve) directly in agents/reviewer.md so it can't silently regress to
    SOLID-only."""
    reviewer = read_skill_file("agents/reviewer.md")
    assert "docs/lens-overlap.md" in reviewer
    assert "clean-architecture" in reviewer


def test_analyze_mode_phase_numbers_dont_collide_with_the_shared_workflow():
    """WS-5 (5.5): ddd's own gates (model keep/discard, stop) are not the shared
    workflow's Phase 3 (decision gate) or Phase 4 (apply) — so they must not be
    labelled "Phase 3"/"Phase 4" in ddd's own prose. Phase 1/Phase 2 do line up
    with the shared workflow's Phase 1/Phase 2 and keep those numbers."""
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    assert (
        "Phase 3 —" not in body
    ), "ddd's model-review gate collides with the shared Phase 3"
    assert (
        "Phase 4 —" not in body
    ), "ddd's stop step collides with the shared Phase 4 (apply)"
    assert "Phase 1 — Analyzer" in body
    assert "Phase 2 — Reviewer" in body
    assert (
        "MODEL REVIEW GATE" in body
    ), "ddd's own gate must still exist, just unnumbered"


def test_memory_capture_points_at_the_mente_skill():
    """WS-5 (5.6): the durable-knowledge capture step invokes /mente, not the
    stale /memory name."""
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    assert "/memory" not in body
    assert "/mente" in body


def test_model_review_gate_flags_the_docs_domain_overwrite_risk():
    """WS-5 (5.6): keep-or-discard must warn before clobbering pre-existing
    docs/domain/ files from an earlier run."""
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    assert "overwrite" in body.lower()
    assert "docs/domain" in body

    reviewer = read_skill_file("agents/reviewer.md")
    assert "pre-existing" in reviewer.lower() or "overwrite" in reviewer.lower()


def test_python_reference_has_no_stale_issue_reference():
    """WS-5 (5.6): drop the dangling repo-issue citation."""
    text = read_skill_file("references/python.md")
    assert "issue #55" not in text
    assert "repository issue" not in text.lower()


def test_ddd_core_covers_the_tactical_spine():
    text = read_skill_file("references/ddd-core.md")
    required_concepts = [
        "Value object",
        "Entities",
        "Aggregate",
        "reference other aggregates by identity",  # the four-rules signature
        "one aggregate per transaction",
        "eventual",
        "Factories",
        "domain event",
        "integration event",
        "Domain service",
        "Application service",
        "Repository",
        "Unit of work",
        "inward",  # dependency direction
        "Do NOT",  # a when-not-to block exists
    ]
    missing = [
        concept for concept in required_concepts if concept.lower() not in text.lower()
    ]
    assert not missing, f"ddd-core.md missing: {missing}"


def section_of(text, heading_prefix):
    """Return the Markdown section starting at `heading_prefix`, up to the next
    heading of the same level. Guards assert against a SECTION, not the whole
    file — otherwise a stray word elsewhere satisfies them and the guard passes
    with the content deleted (issue #153's failure mode)."""
    start = text.find(heading_prefix)
    assert start != -1, f"section missing entirely: {heading_prefix!r}"
    level = len(heading_prefix) - len(heading_prefix.lstrip("#"))
    rest = text[start + len(heading_prefix) :]
    next_heading = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return (rest[: next_heading.start()] if next_heading else rest).lower()


def test_ddd_core_carries_the_specification_pattern():
    """#55: Specification is a first-class tactical pattern — a named business
    predicate that composes, with the repository translating it. Assert the
    composition and the translation seam, not just the word."""
    section = section_of(read_skill_file("references/ddd-core.md"), "## Specification")
    assert "is_satisfied_by" in section, "need the canonical predicate operation"
    for use in ["validation", "selection", "construction"]:
        assert use in section, f"Specification's three uses missing: {use}"
    assert (
        "compose" in section or "combinator" in section
    ), "a Specification that doesn't compose is just a predicate function"
    assert (
        "translat" in section
    ), "the adapter-translates-to-a-query seam is what keeps SQL out of the domain"


def test_ddd_core_carries_the_entity_identity_strategy():
    """#58: identity is a modeling decision, not an afterthought — natural vs
    surrogate, and who mints the id."""
    section = section_of(
        read_skill_file("references/ddd-core.md"), "## Entity identity"
    )
    assert "natural" in section and "surrogate" in section
    assert (
        "application-generated" in section or "app-generated" in section
    ), "need the app- vs db-generated identity tradeoff"
    assert "database-generated" in section or "db-generated" in section
    assert "port" in section, "the identity choice must be tied back to the ports"


def test_ddd_core_distinguishes_the_two_repository_styles():
    """#59: collection-oriented vs persistence-oriented, and how each pairs with
    the unit of work."""
    section = section_of(
        read_skill_file("references/ddd-core.md"), "### Repository semantics"
    )
    assert "collection-oriented" in section
    assert "persistence-oriented" in section
    assert "change tracking" in section or "identity map" in section
    assert "unit of work" in section


def test_ddd_core_covers_modules_named_in_the_ubiquitous_language():
    """#56: packaging is a modeling decision — concept-first vs layer-first."""
    section = section_of(read_skill_file("references/ddd-core.md"), "## Modules")
    assert "concept-first" in section and "layer-first" in section
    assert (
        "ubiquitous language" in section
    ), "the point is that package names belong to the language"
    assert "inward" in section, "the dependency rule still holds inside a module"


def test_ddd_core_covers_the_supple_design_subset():
    """#57: the three highest-leverage Supple Design patterns."""
    section = section_of(read_skill_file("references/ddd-core.md"), "## Supple Design")
    for pattern in ["intention-revealing", "side-effect-free", "assertion"]:
        assert pattern in section, f"supple-design subset missing: {pattern}"


def test_ddd_core_when_not_to_grew_with_every_new_pattern():
    """Every pattern added to the rubric needs its own brake, or the skill just
    got more ceremonious. All five, not a subset — Supple Design is the one most
    likely to breed ceremony, so it is the one that must not be exempt."""
    when_not_to = section_of(
        read_skill_file("references/ddd-core.md"), "## When NOT to"
    )
    for brake in ["specification", "module", "identity", "supple", "cqrs"]:
        assert brake in when_not_to, f"no when-NOT-to brake for: {brake}"


OPT_IN_REFERENCES = {
    "references/cqrs.md": ["cqrs", "read model", "projection", "command"],
    "references/event-sourcing.md": ["event sourcing", "replay", "snapshot", "upcast"],
    "references/sagas.md": ["saga", "process manager", "compensat", "choreograph"],
}


def test_opt_in_references_exist_and_carry_their_core_vocabulary():
    """#60/#61/#62: each opt-in discipline gets its own reference, loaded only
    when opted into."""
    for relative_path, vocabulary in OPT_IN_REFERENCES.items():
        text = read_skill_file(relative_path).lower()
        missing = [term for term in vocabulary if term not in text]
        assert not missing, f"{relative_path} missing: {missing}"


def test_opt_in_references_price_the_pattern_before_recommending_it():
    """The guardrail is 'name them, price them, never reach for them silently' —
    so each file must carry an explicit cost list and a when-NOT-to."""
    for relative_path in OPT_IN_REFERENCES:
        text = read_skill_file(relative_path)
        # headings, not loose substrings: "cost" survives in ordinary prose, so a
        # substring check passes with the whole cost list deleted.
        assert "## When NOT to" in text, f"{relative_path} has no when-NOT-to section"
        costs = section_of(text, "## What it costs")
        assert (
            len(costs.split()) > 60
        ), f"{relative_path}'s cost list is a heading with nothing under it"


def test_cqrs_and_event_sourcing_are_stated_as_independent():
    """The single most common confusion: CQRS does not require ES, and ES is not
    required by DDD. Both files must say so."""
    cqrs = read_skill_file("references/cqrs.md").lower()
    event_sourcing = read_skill_file("references/event-sourcing.md").lower()
    assert "event sourcing" in cqrs and "independent" in cqrs
    assert "not required" in event_sourcing or "does not require" in event_sourcing


def test_cqrs_keeps_query_ports_distinct_from_repositories():
    """ISP + the core rule: a repository returns aggregates, a query port returns
    a read model. Conflating them is how CQRS rots."""
    text = read_skill_file("references/cqrs.md").lower()
    assert "query port" in text
    assert "repositor" in text, "must contrast the query port against the repository"


def test_sagas_depend_on_ports_not_on_a_concrete_bus():
    """DIP for the orchestration layer: dispatch/subscribe are ports; the bus is
    an injected adapter."""
    text = read_skill_file("references/sagas.md").lower()
    assert "port" in text
    assert "bus" in text or "dispatch" in text
    assert "application" in text, "the saga's layer must be stated"
    assert "integration event" in text, "cross-context sagas ride integration events"


def test_skill_md_carries_the_opt_in_triage_step_itself():
    """The routing STEP is the thing under guard, not the reference paths — those
    also appear in the file map and the guardrails, so asserting on them passes
    with the whole step deleted. Assert the step and its load-bearing clauses."""
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    triage = section_of(body, "### 3. 🔀 Opt-in triage")
    assert "default is no" in triage, "the default must be stated as no"
    assert "trigger" in triage, "the step must say what fires it"
    assert (
        "cheap" in triage
    ), "the cheap alternatives must sit OUTSIDE the gated references"
    assert "price it" in triage or "cost list" in triage
    for discipline in ["cqrs", "event sourcing", "saga"]:
        assert discipline in triage, f"triage never names {discipline}"


def test_opt_in_triage_runs_before_the_modeling_gate():
    """These decisions rewrite the ports (and, for ES, the aggregates) the gate
    signs off — deciding after the gate means silently amending an approved
    artifact."""
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    assert body.index("Opt-in triage") < body.index(
        "MODELING GATE"
    ), "the opt-in triage must precede the modeling gate"
    gate = section_of(body, "### 5. 🚦 MODELING GATE")
    assert "identity" in gate, "#58: identity generation is gated, not deferred"
    assert "opt-in" in gate, "the gate must surface the step-3 decision for sign-off"


def test_skill_md_routes_to_the_reference_material_it_added():
    """Content in references/ with no route from SKILL.md is unreachable. Each of
    #56/#57/#58 requires a specific hand-off from design mode."""
    body = parse_frontmatter(read_skill_file("SKILL.md"))["_body"]
    build = section_of(body, "### 6. Build layer-by-layer")
    assert (
        "concept-first" in build or "modules" in build
    ), "#56: the scaffold step must reference the packaging note"
    assert (
        "supple design" in build
    ), "#57: the refactor guidance must aim at Supple Design"


def test_analyzer_hunts_the_newly_documented_smells():
    """A rubric the analyzer can't see is decoration — the new patterns need
    matching violation signatures, each with a way to hunt it. ("query" is NOT
    asserted: it predates this content in the fat-repository bullet, so it would
    prove nothing.)"""
    analyzer = read_skill_file("agents/analyzer.md").lower()
    for signature in ["package-by-layer", "specification", "de-facto cqrs"]:
        assert signature in analyzer, f"analyzer has no signature for: {signature}"
    assert (
        analyzer.count("*hunt:*") >= 3
    ), "a signature with no hunt recipe is not actionable"
    assert (
        "*false positive:*" in analyzer
    ), "the signatures prone to firing at scale must carry an FP guard"


def test_strategic_has_full_context_mapping_catalogue():
    text = read_skill_file("references/strategic.md")
    catalogue = [
        "Partnership",
        "Shared Kernel",
        "Customer/Supplier",
        "Conformist",
        "Anti-Corruption Layer",
        "Open Host Service",
        "Published Language",
        "Separate Ways",
        "Big Ball of Mud",
    ]
    missing = [pattern for pattern in catalogue if pattern.lower() not in text.lower()]
    assert not missing, f"strategic.md context-map catalogue missing: {missing}"
    for anchor in ["event storming", "core", "supporting", "generic"]:
        assert anchor.lower() in text.lower(), f"strategic.md missing: {anchor}"


def test_python_reference_shows_the_core_idioms():
    text = read_skill_file("references/python.md")
    assert "@dataclass(frozen=True)" in text, "need a frozen-dataclass value object"
    assert "Protocol" in text, "need typing.Protocol ports"
    assert "unit of work" in text.lower(), "need a unit-of-work idiom"
    assert re.search(r"class\s+\w*Repository", text), "need a repository class idiom"
    assert re.search(r"class\s+\w*UnitOfWork", text), "need a unit-of-work class idiom"


def test_typescript_reference_shows_the_core_idioms():
    text = read_skill_file("references/typescript.md")
    lowered = text.lower()
    assert "readonly" in lowered, "need readonly (immutable value objects)"
    assert "equals(" in text, "TS has no free value equality — VOs must define equals"
    assert "brand" in lowered, "need branded-type typed identities"
    assert "unit of work" in lowered, "need a unit-of-work idiom"
    assert re.search(r"class\s+\w*Repository", text), "need a repository class idiom"


def test_typescript_reference_gives_the_interface_vs_abstract_class_decision():
    text = read_skill_file("references/typescript.md")
    lowered = text.lower()
    # the TS analogue of ports->Protocol / base-classes->ABC:
    # ports are interfaces, domain base classes are abstract classes
    assert "interface" in lowered and "port" in lowered, "ports are interfaces"
    assert "abstract class" in lowered, "domain base classes use abstract class"
    assert re.search(
        r"abstract\s+class\s+AggregateRoot", text
    ), "need an AggregateRoot abstract-class example to contrast with interface ports"
    assert "promise" in lowered, "TS persistence ports are async (return Promises)"


def test_python_reference_gives_the_protocol_vs_abc_decision():
    text = read_skill_file("references/python.md")
    lowered = text.lower()
    # the explicit rule: ports -> Protocol, domain base classes -> ABC
    assert (
        "ports → protocol" in lowered
        or "ports —> protocol" in lowered
        or ("port" in lowered and "protocol" in lowered and "base class" in lowered)
    ), "need the ports-vs-base-classes rule of thumb"
    assert "abc" in lowered, "need the ABC side of the decision"
    assert re.search(
        r"class\s+AggregateRoot\(ABC\)", text
    ), "need an AggregateRoot ABC example to contrast with Protocol ports"
    assert "runtime_checkable" in text, "must warn about @runtime_checkable's limits"


def test_report_template_has_the_parsed_structure():
    text = read_skill_file("references/report-template.md")
    # Assert one example ID per tier by *shape* (ddd/<tier>-<n>), not literal numbers,
    # so renumbering or re-tiering the template's examples never trips this guard.
    for tier in ("critical", "major", "minor"):
        assert re.search(
            rf"\[ddd/{tier}-\d+\]", text
        ), f"report-template.md missing a ddd/{tier}-<n> example ID"
    for marker in ["Tier", "Reader impact", "Risk", "Status", "pending"]:
        assert marker in text, f"report-template.md missing: {marker}"
    assert "Target architecture sketch" in text


def test_analyze_agents_exist_and_state_their_contracts():
    analyzer = read_skill_file("agents/analyzer.md")
    reviewer = read_skill_file("agents/reviewer.md")
    assert "read-only" in analyzer.lower()
    assert "draft-findings.md" in analyzer
    for signature in ["anemic", "controller", "missing port", "aggregate"]:
        assert (
            signature.lower() in analyzer.lower()
        ), f"analyzer missing signature: {signature}"
    assert "report-template.md" in reviewer
    assert "docs/domain" in reviewer  # reverse-engineered proposal
    assert "discard" in reviewer.lower()  # keep/discard gate
    assert "edit no code" in reviewer.lower() or "no code" in reviewer.lower()


def test_plugin_manifests_advertise_ddd():
    plugin_manifest = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text()
    )
    marketplace_manifest = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text()
    )
    assert (
        "ddd" in plugin_manifest["description"].lower()
        or "domain-driven" in plugin_manifest["description"].lower()
    )
    marketplace_blob = json.dumps(marketplace_manifest).lower()
    assert "ddd" in marketplace_blob or "domain-driven" in marketplace_blob


def test_ddd_evals_cover_modes_and_gates():
    evals_path = REPO_ROOT / "evals" / "ddd-evals.json"
    assert evals_path.is_file(), "evals/ddd-evals.json missing"
    document = json.loads(evals_path.read_text())
    assert document["skill_name"] == "ddd"
    cases = document["evals"]
    assert len(cases) >= 4, "want at least 4 eval cases"
    for case in cases:
        for field in ["id", "prompt", "expected_output", "assertions"]:
            assert field in case, f"eval case {case.get('id')} missing {field}"
        assert isinstance(case["assertions"], list) and case["assertions"]
    blob = json.dumps(document).lower()
    assert "modeling gate" in blob or "modelling gate" in blob
    assert "report-only" in blob or "no code" in blob  # analyze mode
    assert "programmatic" in blob  # tdd handoff
