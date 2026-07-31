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

# An echoed variable piped into an interpreter. The interpreter must be the
# command the pipe feeds, not merely a word somewhere to its right -- see
# test_the_pipe_pattern_matches_commands_not_mentions for the cases that pins.
ECHO_INTO_INTERPRETER = re.compile(
    r'echo "\$[A-Za-z_][A-Za-z0-9_]*"\s*\|\s*'
    r"(?:(?:\S*/)?(?:py|python3?)(?![\w.-])|sh\s+\S*mente-python)"
)


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
    Python JSON parser. Scans every skill, not just config-sync.

    The interpreter is matched by every name a skill may legitimately use --
    the `py` helper, a bare `python`, the banned `python3`, and the launcher
    invoked as `sh .../mente-python` -- so retiring the system interpreter
    cannot quietly retire this guard along with it.

    It must be the COMMAND the pipe feeds, not merely a word appearing after
    it: `echo "$DATA" | grep python` is a perfectly safe line that mentions an
    interpreter, and flagging it would train readers to ignore this guard."""
    offenders = []
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        for line_number, line in enumerate(skill_file.read_text().splitlines(), 1):
            if ECHO_INTO_INTERPRETER.search(line):
                offenders.append(
                    f"  {skill_file.relative_to(SKILLS_DIR)}:{line_number}: {line.strip()}"
                )
    assert not offenders, "echo|python JSON parse (use printf '%s\\n'):\n" + "\n".join(
        offenders
    )


def test_the_pipe_pattern_matches_commands_not_mentions():
    """The guard is only useful if it fires on the broken form and stays quiet
    on safe lines that happen to name an interpreter. A guard that cries wolf
    gets suppressed, which is the same as not having it."""
    broken = [
        'echo "$PLAN" | python3 -c "import json,sys; json.load(sys.stdin)"',
        'echo "$PLAN" | python -c "pass"',
        'echo "$PLAN" | py -c "pass"',
        'echo "$PLAN" | /usr/bin/python3 -c "pass"',
        'echo "$PLAN" | sh "$LAUNCHER"/bin/mente-python -c "pass"',
    ]
    safe = [
        'echo "$PLAN" | grep python',  # mentions an interpreter, feeds grep
        'echo "$PLAN" | jq .',
        'printf \'%s\\n\' "$PLAN" | python3 -c "pass"',  # the sanctioned form
    ]
    for line in broken:
        assert ECHO_INTO_INTERPRETER.search(line), f"should flag: {line}"
    for line in safe:
        assert not ECHO_INTO_INTERPRETER.search(line), f"false positive: {line}"
