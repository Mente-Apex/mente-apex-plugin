"""The prose backend, for suites whose subject is a document.

Without it a documentation-as-code repo gets no gate at all — neither mutmut nor
Stryker will mutate a Markdown heading. Unlike them, this backend generates and
applies its own mutants, over exactly the slice the test declared.

The three operators answer three different questions:
  delete — does the test notice the section is gone at all?
  blank  — does it need the CONTENT, or only the heading?
  invert — does it check what the directive SAYS, or only that a word appears?
"""

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


def _locate(text, heading_text):
    """Return (heading_start, body_start, body_end) for the declared section."""
    heading_pattern = re.compile(
        r"^(#{1,6})\s.*" + re.escape(heading_text) + r".*$", re.MULTILINE
    )
    heading_match = heading_pattern.search(text)
    if heading_match is None:
        raise ValueError(f"heading containing {heading_text!r} not found")
    level = len(heading_match.group(1))
    body_start = heading_match.end()
    next_heading = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE).search(
        text, body_start
    )
    body_end = next_heading.start() if next_heading else len(text)
    return heading_match.start(), body_start, body_end


def extract_section(text, heading_text):
    """The text between a heading and the next same-or-higher-level heading."""
    _, body_start, body_end = _locate(text, heading_text)
    return text[body_start:body_end]


def _invert(body):
    """Flip directive polarity once per occurrence, longest token first."""
    pattern = re.compile("|".join(re.escape(word) for word, _ in INVERSIONS))
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
    """
    import json
    import subprocess

    result = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "--collect-only",
            "-q",
            "--covers-manifest=-",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    return tuple(tuple(entry) for entry in json.loads(result.stdout or "[]"))
