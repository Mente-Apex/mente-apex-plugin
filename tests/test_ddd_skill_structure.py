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
    # version lives under metadata: — assert the literal line is present in body-adjacent frontmatter
    frontmatter_text = read_skill_file("SKILL.md").split("---")[1]
    assert re.search(
        r'version:\s*"0\.1\.0"', frontmatter_text
    ), "metadata.version must be 0.1.0"


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
    for marker in ["Tier", "Impact", "Status", "pending"]:
        assert marker in text, f"report-template.md missing: {marker}"
    assert "Target architecture sketch" in text


def test_analyze_agents_exist_and_state_their_contracts():
    analyzer = read_skill_file("agents/analyzer.md")
    reviewer = read_skill_file("agents/reviewer.md")
    assert "read-only" in analyzer.lower()
    assert "findings-draft.md" in analyzer
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
