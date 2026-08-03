"""A mechanical guard that the repo's own Python is black-clean.

README.md and every plan in this repo state that the formatter and the linter
must be clean before a commit, and nothing enforced it — so the rule held only
for as long as each contributor remembered it, and it had already stopped
holding. A convention nothing checks is a convention that has already drifted.

Black is invoked through `sys.executable -m black` rather than `uv run black`:
the test is already running inside the environment uv built, and re-entering uv
from within it resolves the project a second time for no benefit.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The directories whose Python this project owns and formats. Vendored or
# generated trees are deliberately absent: black's own config excludes the
# skill eval workspaces, and naming the owned directories here means a stray
# unformatted file outside them can never make this guard fail for the wrong
# reason.
FORMATTED_DIRECTORIES = (
    "hooks",
    "scripts",
    "tests",
    "skills/menteapex-deliverable/scripts",
)


def test_the_repo_is_black_clean():
    """`uv run black --check scripts/ tests/` must pass.

    The failure message names the offending files, because "black would
    reformat something" is not actionable and "run black on these three files"
    is.
    """
    targets = [
        directory
        for directory in FORMATTED_DIRECTORIES
        if (REPO_ROOT / directory).is_dir()
    ]
    assert targets, "no formatted directories found — has the layout changed?"

    completed = subprocess.run(
        [sys.executable, "-m", "black", "--check", *targets],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if completed.returncode == 0:
        return

    combined_output = completed.stdout + completed.stderr
    offenders = [
        line.split("would reformat", 1)[1].strip()
        for line in combined_output.splitlines()
        if line.startswith("would reformat")
    ]
    assert completed.returncode == 1 and offenders, (
        "could not run black — it is a declared dev dependency, so this is a "
        f"broken environment rather than a formatting failure:\n{combined_output}"
    )
    raise AssertionError(
        "black would reformat these files — run `uv run black "
        f"{' '.join(targets)}` before committing:\n  " + "\n  ".join(offenders)
    )
