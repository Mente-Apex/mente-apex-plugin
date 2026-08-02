"""README must document the probe now that it is invokable — the duty spec
§4.4 defers until the behavior exists."""

from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


class TestTheReadmeDocumentsTheProbe:
    def test_it_names_the_script(self):
        assert "complexity_probe.py" in README

    def test_it_shows_the_three_entry_points(self):
        assert "--gate" in README
        assert "--sink review" in README
        assert "--json" in README

    def test_it_states_the_gate_rule(self):
        assert "silence" in README.lower()
