"""Structural guard for the clean-architecture lens and the shared overlap hub.

Authored prose, not runtime code: assert files exist and carry the sections the
orchestration and the plugin loader depend on. Dependency-free (no PyYAML).
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CA_SKILL_DIR = REPO_ROOT / "skills" / "clean-architecture"
LENS_OVERLAP = REPO_ROOT / "docs" / "lens-overlap.md"


def read_skill_file(relative_path):
    """Read a file under skills/clean-architecture/, failing the test if absent."""
    target = CA_SKILL_DIR / relative_path
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


def test_lens_overlap_hub_replaces_pairwise_map():
    assert LENS_OVERLAP.is_file(), "docs/lens-overlap.md must exist"
    assert not (REPO_ROOT / "docs" / "solid-gof-overlap.md").exists(), \
        "docs/solid-gof-overlap.md must be gone (migrated to lens-overlap.md)"
    text = LENS_OVERLAP.read_text(encoding="utf-8")
    # the hub adds clean-architecture as a participating lens
    assert "clean-architecture" in text.lower(), "hub must carry clean-architecture rows"
    # the SOLID<->GoF content survives the move (spot-check canonical entries)
    for kept in ["Strategy", "Singleton", "Abstract Factory", "DIP"]:
        assert kept in text, f"hub lost SOLID/GoF content: {kept}"


def test_no_stale_overlap_references_remain():
    offenders = []
    scan_dirs = ["skills/solid", "skills/gof", "docs/refactor-workflow.md",
                 "docs/refactor-agents", "README.md", "tests/test_skill_integrity.py"]
    for scan in scan_dirs:
        target = REPO_ROOT / scan
        files = target.rglob("*") if target.is_dir() else [target]
        for candidate in files:
            if (
                candidate.is_file()
                and candidate.suffix in {".md", ".py"}
                and "solid-gof-overlap" in candidate.read_text(encoding="utf-8")
            ):
                offenders.append(str(candidate.relative_to(REPO_ROOT)))
    assert not offenders, f"stale solid-gof-overlap references remain: {offenders}"


def test_skill_md_declares_tiers_tooling_and_carve():
    fields = parse_frontmatter(read_skill_file("SKILL.md"))
    assert fields.get("name") == "clean-architecture"
    assert fields.get("user-invocable") == "true"
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert re.search(r'version:\s*"0\.1\.0"', frontmatter_text)
    body = read_skill_file("SKILL.md")
    lowered = body.lower()
    for marker in ["headline", "secondary", "appendix", "opt-in"]:
        assert marker in lowered, f"SKILL.md missing tier marker: {marker}"
    assert "audit" in lowered and "no build" in lowered, "must state audit-first, no build mode"
    for tool in ["grimp", "import-linter"]:
        assert tool in lowered, f"SKILL.md missing tooling reference: {tool}"
    assert "degrade" in lowered or "fallback" in lowered, "must state graceful fallback"
    assert "lens-overlap.md" in body and "refactor-workflow.md" in body
    assert "ddd" in lowered, "must state the carve with ddd"


def test_principles_cover_the_tiered_rubric():
    text = read_skill_file("references/principles.md")
    required = [
        "Dependency Rule", "ADP", "SDP", "SAP",
        "REP", "CCP", "CRP",
        "Screaming Architecture", "composition root",
        "Instability", "Main Sequence",
        "approximate",             # the metrics caveat (now language-neutral)
        "When NOT",                # judgment block
    ]
    missing = [concept for concept in required if concept.lower() not in text.lower()]
    assert not missing, f"principles.md missing: {missing}"
    for tier in ["Headline", "Secondary", "Appendix", "Critical", "Major", "Minor"]:
        assert tier in text, f"principles.md missing tier label: {tier}"


def test_python_reference_covers_tooling_and_degrade():
    text = read_skill_file("references/python.md")
    lowered = text.lower()
    for tool in ["grimp", "import-linter", "importlinter.ini", "dependency-cruiser"]:
        assert tool in lowered, f"python.md missing tool: {tool}"
    assert "fan-in" in lowered and "fan-out" in lowered, "must show how to compute Instability"
    assert "degrade" in lowered or "fallback" in lowered, "must give the no-tool degrade path"
    assert "runtime_checkable" not in text  # sanity: this is CA, not the ddd port ref


def test_typescript_reference_covers_tooling_and_degrade():
    text = read_skill_file("references/typescript.md")
    lowered = text.lower()
    for tool in ["dependency-cruiser", "madge", ".dependency-cruiser"]:
        assert tool in lowered, f"typescript.md missing tool: {tool}"
    assert "fan-in" in lowered and "fan-out" in lowered, "must show how to compute Instability"
    assert "degrade" in lowered or "fallback" in lowered, "must give the no-tool degrade path"
    assert "erased" in lowered, "must state the interfaces-erased abstractness caveat for TS"


def test_report_template_has_structure_contract_and_appendix():
    text = read_skill_file("references/report-template.md")
    # Assert one example ID per tier by *shape* (clean-arch/<tier>-<n>), not literal
    # numbers, so renumbering or re-tiering the examples never trips this guard.
    for tier in ("critical", "major", "minor"):
        assert re.search(rf"\[clean-arch/{tier}-\d+\]", text), \
            f"report-template.md missing a clean-arch/{tier}-<n> example ID"
    for marker in ["Tier", "Status", "pending",
                   "Dependency-rule contract", "Analysis mode", "Structural health"]:
        assert marker in text, f"report-template.md missing: {marker}"


def test_agents_state_their_contracts():
    analyzer = read_skill_file("agents/analyzer.md")
    reviewer = read_skill_file("agents/reviewer.md")
    implementer = read_skill_file("agents/implementer.md")
    assert "read-only" in analyzer.lower()
    assert "findings-draft.md" in analyzer
    assert "principles.md" in analyzer
    # agent docs must follow the detect-and-load convention, not hardcode one language
    assert "<language>.md" in analyzer, "analyzer must load references/<language>.md"
    assert "typescript.md" in analyzer and "python.md" in analyzer, \
        "analyzer must not have regressed to Python-only"
    assert "report-template.md" in reviewer
    assert "lens-overlap.md" in reviewer                     # cross-reference the hub
    assert "<language>.md" in reviewer, "reviewer must load references/<language>.md"
    assert "dependency-rule contract" in reviewer.lower()    # language-neutral contract
    assert "importlinter" in reviewer.lower() and "dependency-cruiser" in reviewer.lower(), \
        "reviewer must name both the Python and JS/TS contract tools"
    assert "mechanical" in implementer.lower() and "refactor-jobs.md" in implementer
    assert "advisory" in implementer.lower() or "opt-in" in implementer.lower()


def test_ca_evals_cover_tiers_tooling_and_carve():
    evals_path = REPO_ROOT / "evals" / "clean-architecture-evals.json"
    assert evals_path.is_file(), "evals/clean-architecture-evals.json missing"
    document = json.loads(evals_path.read_text())
    assert document["skill_name"] == "clean-architecture"
    cases = document["evals"]
    assert len(cases) >= 4
    for case in cases:
        for field in ["id", "skill", "prompt", "expected_output", "assertions"]:
            assert field in case, f"eval case {case.get('id')} missing {field}"
        assert isinstance(case["assertions"], list) and case["assertions"]
    blob = json.dumps(document).lower()
    assert "dependency rule" in blob
    assert "opt-in" in blob or "--cohesion" in blob or "--metrics" in blob
    assert "import-linter" in blob
    assert "ddd" in blob                      # the carve


def test_manifests_advertise_ca_and_versions_are_bumped():
    plugin_manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    marketplace_manifest = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert "clean-architecture" in plugin_manifest["description"].lower()
    assert "clean-architecture" in plugin_manifest["keywords"]
    marketplace_blob = json.dumps(marketplace_manifest).lower()
    assert "clean-architecture" in marketplace_blob
    # Versions must stay mirrored and never regress below the release that
    # introduced clean-architecture (0.13.0). Pinning the exact literal made this
    # break on every subsequent bump, so assert lockstep + floor instead.
    plugin_version = plugin_manifest["version"]
    marketplace_version = marketplace_manifest["plugins"][0]["version"]
    assert plugin_version == marketplace_version
    def to_tuple(semver):
        return tuple(int(part) for part in semver.split("."))

    assert to_tuple(plugin_version) >= (0, 13, 0)
