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
import os
import re
import subprocess
import warnings
from pathlib import Path, PurePosixPath

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


def _delete_section(text, heading_start, body_start, body_end):
    return text[:heading_start] + text[body_end:]


def _blank_section(text, heading_start, body_start, body_end):
    return text[:body_start] + "\n\n(section body removed)\n\n" + text[body_end:]


def _invert_section(text, heading_start, body_start, body_end):
    return text[:body_start] + _invert(text[body_start:body_end]) + text[body_end:]


OPERATORS = {
    "delete": _delete_section,
    "blank": _blank_section,
    "invert": _invert_section,
}


def mutate(text, heading_text, operator):
    """Return `text` with the declared slice mutated by `operator`."""
    heading_start, body_start, body_end = _locate(text, heading_text)
    apply_operator = OPERATORS.get(operator)
    if apply_operator is None:
        raise ValueError(f"unknown operator: {operator!r}")
    return apply_operator(text, heading_start, body_start, body_end)


def prose_survivors(repo_root, declarations, run_test):
    """Apply each operator to each declared slice; report what stayed green.

    `declarations` is (test_node_id, artifact_path, section) triples, collected
    from @pytest.mark.covers. `run_test` returns True when the test still
    passes — a True under a mutant means the guard did not notice, which is the
    definition of vacuous.

    Restore is try/finally over the original text held in memory, never a git
    operation: the harness must be safe on a dirty tree, and a checkout would
    eat unrelated work.

    An operator that leaves the slice byte-identical produced no mutant at all,
    and a mutant that was never applied cannot be one "these tests failed to
    kill". `invert` on a slice containing no directive token is the reproduced
    case -- it made two thirds of this repo's own reported survivors false
    positives. Such a case is neither run nor reported as a survivor: it is
    emitted with status `no_op_mutant`, which lands in the report's
    Inconclusive section naming the operator, so "invert had nothing to flip
    here" stays distinguishable from "invert ran and the guard killed it".
    Dropping it silently would trade one silence for another.
    """
    survivors = []
    for node_id, artifact_path, section in declarations:
        artifact = Path(repo_root) / artifact_path
        original = artifact.read_text(encoding="utf-8")
        for operator in OPERATORS:
            mutated = mutate(original, section, operator=operator)
            if mutated == original:
                survivors.append(
                    Survivor(
                        artifact=artifact_path,
                        location=f"{artifact_path} § {section}",
                        mutant=operator,
                        associated_tests=(node_id,),
                        backend="prose",
                        granularity="section",
                        status="no_op_mutant",
                    )
                )
                continue
            try:
                artifact.write_text(mutated, encoding="utf-8")
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


COVERS_PLUGIN = "mutation_gate_covers_plugin"

_PLUGIN_DIR = str(Path(__file__).resolve().parent)


def _collect_command(manifest_path):
    """The pytest argv and env that make `--covers-manifest` exist anywhere.

    The option is registered by `mutation_gate_covers_plugin`, which SHIPS
    WITH THE GATE rather than being borrowed from the audited repo's
    conftest. Loading it with `-p` (and putting `scripts/` on the
    subprocess's `PYTHONPATH` so `-p` can import it) is what lets the prose
    backend run against a repo that has never heard of this plugin: before
    this, pytest exited 4 with "unrecognized arguments" everywhere except
    this one repository.

    `PYTHONPATH` is extended, never replaced -- an audited repo may well
    depend on its own entry, and clobbering it would break its collection in
    a way that looks exactly like "this repo has no markers".
    """
    existing = os.environ.get("PYTHONPATH", "")
    env = {
        **os.environ,
        "PYTHONPATH": (
            _PLUGIN_DIR + os.pathsep + existing if existing else _PLUGIN_DIR
        ),
    }
    argv = [
        "uv",
        "run",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        COVERS_PLUGIN,
        f"--covers-manifest={manifest_path}",
    ]
    return argv, env


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
    second behind the first. The raise is caught one level up, in
    `ProseBackend.survivors`, and turned into a `run_errors` entry -- the
    failure must be loud, but it must not abort a run whose other backends
    have already produced findings.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as scratch_dir:
        manifest_path = Path(scratch_dir) / "covers-manifest.json"
        argv, env = _collect_command(manifest_path)
        result = subprocess.run(
            argv,
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
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


def _normalize_repo_path(path):
    """Normalize a repo-relative path for comparing across representations.

    Git-produced selection paths and `@pytest.mark.covers`-declared artifact
    paths should always name the same file the same way, but nothing enforces
    that -- a harmless leading "./", or `os.sep`-joined separators on a
    platform that isn't POSIX, would make an exact `==` fail even though both
    sides mean the same file. That silently dropped a legitimate prose guard
    from the run instead of matching it, so both sides go through this before
    comparing.
    """
    return PurePosixPath(str(path).replace("\\", "/")).as_posix().removeprefix("./")


class ProseBackend:
    """Always available — the mutators ship with the plugin."""

    stack = "prose"
    tool = "built-in"

    def __init__(self, collect=None, run_test=None):
        """Collaborators are injected, defaulting to the module-level pair.

        The defaults are resolved here, at call time, rather than bound as
        eager parameter defaults: `_pytest_still_green` is defined below this
        class, so an eager default couldn't reference it, and — just as
        important — tests monkeypatch `mutation_gate_prose.collect_declarations`
        at the module level, which an eagerly-bound default would silently
        stop seeing (it would have already captured the pre-patch function
        object at class-definition time).
        """
        self._collect = collect or collect_declarations
        self._run_test = run_test or _pytest_still_green
        self._run_errors = ()

    def available(self, repo_root):
        return True

    def install_hint(self, repo_root):
        return ""

    def run_errors(self, repo_root):
        """Run-level facts from the most recent `survivors()` call.

        Empty unless that call could not collect the audited repo's marker
        declarations at all -- see `survivors()`. Same contract as the mutmut
        and Stryker backends': one named fact, reported once.
        """
        return self._run_errors

    def survivors(self, repo_root, paths):
        """Mutate every declared slice whose artifact is in this partition.

        A collection that never completed degrades to a `run_errors` entry
        rather than propagating. It used to raise straight out of `run_gate`,
        aborting the ENTIRE run and discarding every survivor the mutmut and
        Stryker backends had already produced -- a whole audit lost to one
        backend's environment. Every other external-tool failure in this
        codebase degrades; this one did not. It stays loud (a named
        `run_errors` fact and a warning, never an empty-and-therefore-clean
        result), it just no longer takes the run down with it.
        """
        normalized_selection = {_normalize_repo_path(path) for path in paths}
        try:
            collected = self._collect(repo_root)
        except Exception as exc:  # noqa: BLE001 -- any collection failure degrades
            self._run_errors = (
                f"the prose backend could not collect @pytest.mark.covers "
                f"declarations from {repo_root}, so no prose result from this "
                f"run can be trusted -- no Markdown slice was mutated: {exc}",
            )
            warnings.warn(self._run_errors[0], stacklevel=2)
            return ()
        self._run_errors = ()
        declarations = [
            declaration
            for declaration in collected
            if _normalize_repo_path(declaration[1]) in normalized_selection
        ]

        return prose_survivors(
            repo_root,
            declarations,
            run_test=lambda node_id: self._run_test(repo_root, node_id),
        )


def _pytest_still_green(repo_root, node_id):
    """True when the single declared test still passes under the mutant.

    `repo_root` here is always the isolated workspace `ProseBackend.survivors`
    was invoked over -- never the operator's real tree, regardless of the
    directory the calling *process* itself happens to be running from.
    Nothing in this codebase ever `os.chdir`s, so a runner that omits `cwd`
    runs pytest wherever launched `mutation_gate.py`'s process started; since
    the mutant written by `prose_survivors` only ever exists inside the
    workspace copy, that would silently exercise the pristine, unmutated
    source every time and report a "survivor" for every guard whose baseline
    already passes -- an isolation breach that also makes the backend measure
    nothing at all.
    """
    result = subprocess.run(
        ["uv", "run", "pytest", node_id, "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
