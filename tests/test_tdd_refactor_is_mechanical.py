"""The REFACTOR step must name the probe command and the say-why-or-block rule.
A structure test, matching the repo's other skill-contract tests."""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills/tdd/SKILL.md"


def refactor_section() -> str:
    text = SKILL.read_text()
    start = text.index("#### 3. REFACTOR")
    # Look for next heading at any level (###, ####, etc)
    lines = text[start:].split("\n")
    for idx, line in enumerate(lines[1:], 1):  # Skip the section header itself
        if line.startswith("#"):
            end = start + sum(len(line_content) + 1 for line_content in lines[:idx])
            return text[start:end]
    # If no next heading found, return to end of file
    return text[start:]


class TestTheRefactorStepIsMechanical:
    def test_it_names_the_probe_command(self):
        assert "complexity_probe.py" in refactor_section()

    def test_it_states_the_gate_rule(self):
        section = refactor_section().lower()
        assert "state why" in section or "say why" in section

    def test_it_still_says_silence_is_the_failure(self):
        assert "silence" in refactor_section().lower()

    def test_the_seven_judgment_items_survive(self):
        section = refactor_section()
        for item in (
            "Names",
            "Functions",
            "Duplication",
            "Nesting",
            "Responsibility drift",
            "Dependency direction",
            "Mocking as a design signal",
        ):
            assert item in section

    def test_it_does_not_promise_a_threshold(self):
        """The plugin ships no numbers; the step must not imply one."""
        section = refactor_section()
        assert "CC > " not in section
        assert "CC>" not in section
