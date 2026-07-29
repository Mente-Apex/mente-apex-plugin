"""The prose backend, for suites whose subject is a document.

Without it a documentation-as-code repo gets no gate at all — neither mutmut nor
Stryker will mutate a Markdown heading. Unlike them, this backend generates and
applies its own mutants, over exactly the slice the test declared.

The three operators answer three different questions:
  delete — does the test notice the section is gone at all?
  blank  — does it need the CONTENT, or only the heading?
  invert — does it check what the directive SAYS, or only that a word appears?
"""

import json
import re
from pathlib import Path

from mutation_gate import Survivor

INVERSIONS = (
    ("MUST NOT", "MUST"),
    ("MUST", "MUST NOT"),
    ("Do NOT", "Do"),
    ("never", "always"),
    ("always", "never"),
)

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})\s")


def _fenced_flags(lines):
    """One bool per line: True when that line sits inside a ``` or ~~~ fence.

    A `#`-prefixed comment inside a fenced code block is not a Markdown
    heading. Treating it as one truncates (or misidentifies) the declared
    section — precisely the windowing bug this backend exists to catch — so
    every heading search below consults this mask rather than scanning raw
    text.
    """
    in_fence = False
    flags = []
    for line in lines:
        if _FENCE_RE.match(line.lstrip()):
            flags.append(True)  # the fence marker line itself, irrelevant either way
            in_fence = not in_fence
        else:
            flags.append(in_fence)
    return flags


def _locate(text, heading_text):
    """Return (heading_start, body_start, body_end) for the declared section.

    Matching is substring-with-boundaries rather than exact: real headings
    carry trailing prose a marker need not repeat in full (e.g. the SKILL.md
    heading "## Applying is guarded by two gates (the reason this lens is
    report-first)" is declared as just "Applying is guarded by two gates").
    The `\\b` boundaries stop that leniency from also matching a heading that
    merely shares a prefix, like "Step 2" inside "## Step 20".
    """
    lines = text.splitlines(keepends=True)
    fenced = _fenced_flags(lines)
    boundary_pattern = re.compile(r"\b" + re.escape(heading_text) + r"\b")

    pos = 0
    heading_index = heading_start = heading_end = level = None
    for i, line in enumerate(lines):
        if not fenced[i]:
            heading_match = _HEADING_RE.match(line)
            if heading_match and boundary_pattern.search(line):
                heading_index = i
                heading_start = pos
                heading_end = pos + len(line)
                level = len(heading_match.group(1))
                break
        pos += len(line)
    if heading_start is None:
        raise ValueError(f"heading containing {heading_text!r} not found")

    body_start = heading_end
    body_end = len(text)
    next_heading_re = re.compile(r"^#{1," + str(level) + r"}\s")
    pos = body_start
    for j in range(heading_index + 1, len(lines)):
        line = lines[j]
        if not fenced[j] and next_heading_re.match(line):
            body_end = pos
            break
        pos += len(line)
    return heading_start, body_start, body_end


def extract_section(text, heading_text):
    """The text between a heading and the next same-or-higher-level heading."""
    _, body_start, body_end = _locate(text, heading_text)
    return text[body_start:body_end]


def _invert(body):
    """Flip directive polarity once per occurrence, longest token first.

    "Longest first" is enforced by sorting on length rather than relying on
    `INVERSIONS`' declaration order, so a future entry added in the wrong
    order can't silently let a shorter alternative shadow a longer one.
    Each alternative is `\\b`-bounded so it only matches a standalone word or
    phrase — otherwise "never" matches inside "whenever", corrupting prose
    the operator was never meant to touch.
    """
    ordered = sorted(INVERSIONS, key=lambda pair: len(pair[0]), reverse=True)
    pattern = re.compile(
        "|".join(r"\b" + re.escape(word) + r"\b" for word, _ in ordered)
    )
    replacements = dict(INVERSIONS)
    return pattern.sub(lambda m: replacements[m.group(0)], body)


def mutate(text, heading_text, operator):
    """Return `text` with the declared slice mutated by `operator`."""
    heading_start, body_start, body_end = _locate(text, heading_text)
    if operator == "delete":
        return text[:heading_start] + text[body_end:]
    if operator == "blank":
        return text[:body_start] + "\n\n(section body removed)\n\n" + text[body_end:]
    if operator == "invert":
        return text[:body_start] + _invert(text[body_start:body_end]) + text[body_end:]
    raise ValueError(f"unknown operator: {operator!r}")


OPERATORS = ("delete", "blank", "invert")


def prose_survivors(repo_root, declarations, run_test):
    """Apply each operator to each declared slice; report what stayed green.

    `declarations` is (test_node_id, artifact_path, section) triples, collected
    from @pytest.mark.covers. `run_test` returns True when the test still
    passes — a True under a mutant means the guard did not notice, which is the
    definition of vacuous.

    Restore is try/finally over the original text held in memory, never a git
    operation: the harness must be safe on a dirty tree, and a checkout would
    eat unrelated work.
    """
    survivors = []
    for node_id, artifact_path, section in declarations:
        artifact = Path(repo_root) / artifact_path
        original = artifact.read_text(encoding="utf-8")
        for operator in OPERATORS:
            try:
                artifact.write_text(
                    mutate(original, section, operator=operator), encoding="utf-8"
                )
                still_green = run_test(node_id)
            finally:
                artifact.write_text(original, encoding="utf-8")
            if still_green:
                survivors.append(
                    Survivor(
                        artifact=artifact_path,
                        location=f"{artifact_path} § {section}",
                        mutant=operator,
                        associated_tests=(node_id,),
                        backend="prose",
                        granularity="section",
                        # Presence-only guards legitimately survive inversion,
                        # so that operator reports at a lower tier.
                        status=(
                            "survived" if operator != "invert" else "survived_minor"
                        ),
                    )
                )
    return tuple(survivors)


def collect_declarations(repo_root):
    """Read @pytest.mark.covers declarations out of the suite.

    `pytest --collect-only -q` plus the marker's own arguments; a test with no
    marker yields nothing, which is what makes it "unverifiable by construction"
    rather than a failure.

    The manifest travels through a real file, never stdout: `-q
    --collect-only` prints pytest's own collected-node-id list before the
    hook's payload and a "N tests collected" summary line after it, so
    `--covers-manifest=-` cannot be parsed back out of `stdout` — a distinct
    file cannot be polluted by pytest's own output.

    A nonzero exit is raised, not folded into `()`: an empty manifest means
    "no test declared a marker" (unverifiable by design), a pytest crash
    means something is actually broken, and collapsing the two hides the
    second behind the first.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as scratch_dir:
        manifest_path = Path(scratch_dir) / "covers-manifest.json"
        result = subprocess.run(
            [
                "uv",
                "run",
                "pytest",
                "--collect-only",
                "-q",
                f"--covers-manifest={manifest_path}",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"pytest collection failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )
        if not manifest_path.exists():
            return ()
        payload = manifest_path.read_text(encoding="utf-8")
    return tuple(tuple(entry) for entry in json.loads(payload or "[]"))
