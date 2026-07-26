"""Regression guard for #45.

`echo "$VAR"` reinterprets backslash escapes under zsh and POSIX sh, so any JSON
value containing an escape (e.g. a `\\n` inside a plugins-apply `message`) is
corrupted into a raw control character that strict `json.loads` rejects. Engine
JSON must be emitted with `printf '%s\\n'`, which passes the operand through
verbatim. These tests lock that in so the pattern cannot silently return.
"""

import re
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
CONFIG_SYNC_SKILL = SKILLS_DIR / "config-sync" / "SKILL.md"

# Variables that hold engine JSON in config-sync/SKILL.md — none may be echoed.
JSON_BEARING_VARS = ["EXPORT_OUT", "APPLY", "PLAN", "APPLIED_PLUGINS", "SHARED_RESULT"]


def test_json_vars_never_emitted_via_echo():
    offenders = []
    for line_number, line in enumerate(CONFIG_SYNC_SKILL.read_text().splitlines(), 1):
        for json_var in JSON_BEARING_VARS:
            if re.search(rf'echo "\${json_var}"', line):
                offenders.append(f"  L{line_number}: ${json_var} — {line.strip()}")
    assert not offenders, (
        "JSON-bearing vars emitted via echo (corrupts \\n under zsh; use printf '%s\\n'):\n"
        + "\n".join(offenders)
    )


def test_no_skill_pipes_echoed_var_into_python():
    """The definitively-broken form: piping an echoed variable straight into a
    Python JSON parser. Scans every skill, not just config-sync."""
    unsafe = re.compile(r'echo "\$[A-Za-z_][A-Za-z0-9_]*"\s*\|\s*python3')
    offenders = []
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        for line_number, line in enumerate(skill_file.read_text().splitlines(), 1):
            if unsafe.search(line):
                offenders.append(
                    f"  {skill_file.relative_to(SKILLS_DIR)}:{line_number}: {line.strip()}"
                )
    assert not offenders, "echo|python3 JSON parse (use printf '%s\\n'):\n" + "\n".join(
        offenders
    )
