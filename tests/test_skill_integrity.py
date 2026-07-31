"""Static structural guards for the plugin's skills, shared docs, and manifests.

No engine import: these are pure file checks. They protect the refactor
ecosystem's shared-docs architecture (a skill pointing at
docs/refactor-workflow.md must not dangle) and keep the three version mirrors
in lockstep. Narrative docs under docs/superpowers/ (plans, specs) are out of
scope — they carry intentional forward-references and fenced example links.
"""

import json
import re
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DOCS_DIR = REPO_ROOT / "docs"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"

REQUIRED_FRONTMATTER_KEYS = ("name", "description")

GOF_PATTERNS = [
    "Abstract Factory",
    "Builder",
    "Factory Method",
    "Prototype",
    "Singleton",
    "Adapter",
    "Bridge",
    "Composite",
    "Decorator",
    "Facade",
    "Flyweight",
    "Proxy",
    "Chain of Responsibility",
    "Command",
    "Interpreter",
    "Iterator",
    "Mediator",
    "Memento",
    "Observer",
    "State",
    "Strategy",
    "Template Method",
    "Visitor",
]

# The cross-references this guard protects: every refactor lens's skill files
# and the shared docs they point at. All four lenses (clean-architecture,
# clean-code, ddd, gof, solid) plus tdd are scanned so a wrong ../ depth in any
# of them is caught mechanically. Files created by later tasks simply don't
# match yet.
INTEGRITY_SCAN_GLOBS = (
    "skills/clean-architecture/**/*.md",
    "skills/clean-code/**/*.md",
    "skills/code-quality/**/*.md",
    "skills/ddd/**/*.md",
    "skills/gof/**/*.md",
    "skills/solid/**/*.md",
    "skills/tdd/**/*.md",
    "skills/ship/SKILL.md",
    "skills/release/**/*.md",
    "docs/refactor-workflow.md",
    "docs/refactor-agents/*.md",
    "docs/lens-overlap.md",
    "docs/git-convention.md",
    "docs/git-remote-resolution.md",
)

MARKDOWN_LINK = re.compile(r"\]\(([^)]+)\)")
# Backtick-quoted relative doc paths (e.g. `../../../docs/lens-overlap.md`) are
# live cross-references too — a rubric that cites the hub in inline code dangles
# just as badly as a []() link. Only paths starting ./ or ../ and ending .md
# qualify, so prose code spans and fenced example tokens never false-positive.
CODE_RELATIVE_MD_LINK = re.compile(r"`(\.{1,2}/[^`]+?\.md)`")


def _parse_frontmatter(markdown_text):
    """Return the raw YAML frontmatter between the first two '---' fences, or None."""
    if not markdown_text.startswith("---"):
        return None
    fence_end = markdown_text.find("\n---", 3)
    if fence_end == -1:
        return None
    return markdown_text[3:fence_end]


def _integrity_scan_files():
    """Existing Markdown files whose links this guard resolves (dedup, sorted)."""
    matched = set()
    for glob_pattern in INTEGRITY_SCAN_GLOBS:
        for markdown_file in REPO_ROOT.glob(glob_pattern):
            if markdown_file.is_file():
                matched.add(markdown_file)
    return sorted(matched)


def _strip_fenced_code_blocks(markdown_text):
    """Drop ``` fenced blocks so example links inside them aren't treated as live pointers."""
    kept_lines = []
    inside_fence = False
    for line in markdown_text.splitlines():
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            continue
        if not inside_fence:
            kept_lines.append(line)
    return "\n".join(kept_lines)


def _relative_link_targets(markdown_text):
    """Yield each relative link target — []() links and backtick-quoted relative
    .md paths alike (fenced blocks stripped, anchors removed, URLs skipped)."""
    body = _strip_fenced_code_blocks(markdown_text)
    for raw_target in MARKDOWN_LINK.findall(body):
        target = raw_target.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        yield target
    for code_target in CODE_RELATIVE_MD_LINK.findall(body):
        yield code_target.split("#", 1)[0].strip()


def test_every_skill_has_required_frontmatter():
    offenders = []
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        frontmatter = _parse_frontmatter(skill_file.read_text())
        if frontmatter is None:
            offenders.append(f"{skill_file.relative_to(REPO_ROOT)}: no frontmatter")
            continue
        for required_key in REQUIRED_FRONTMATTER_KEYS:
            if not re.search(rf"^{required_key}:", frontmatter, re.MULTILINE):
                offenders.append(
                    f"{skill_file.relative_to(REPO_ROOT)}: missing '{required_key}'"
                )
    assert not offenders, "Frontmatter problems:\n" + "\n".join(offenders)


def test_relative_markdown_links_resolve():
    offenders = []
    for markdown_file in _integrity_scan_files():
        for target in _relative_link_targets(markdown_file.read_text()):
            resolved = (markdown_file.parent / target).resolve()
            if not resolved.exists():
                offenders.append(f"{markdown_file.relative_to(REPO_ROOT)} -> {target}")
    assert not offenders, "Dangling relative markdown links:\n" + "\n".join(offenders)


def test_relative_link_targets_include_inline_code_paths():
    """The resolver treats backtick-quoted relative .md paths as live links too
    (the wrong-../-depth class caught in review), without flagging ordinary code
    spans."""
    sample = (
        "See [workflow](../docs/refactor-workflow.md) and cross-reference "
        "`../../../docs/lens-overlap.md`; ignore `some_var` and `pkg.method`."
    )
    found = set(_relative_link_targets(sample))
    assert "../docs/refactor-workflow.md" in found  # []() link
    assert "../../../docs/lens-overlap.md" in found  # backtick relative .md path
    assert (
        "some_var" not in found and "pkg.method" not in found
    )  # non-path code spans ignored


def test_version_mirrors_match():
    plugin_version = json.loads(PLUGIN_JSON.read_text())["version"]
    pyproject_version = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    marketplace_version = json.loads(MARKETPLACE_JSON.read_text())["plugins"][0][
        "version"
    ]
    assert plugin_version == pyproject_version == marketplace_version, (
        f"version drift — plugin.json={plugin_version} "
        f"pyproject={pyproject_version} marketplace={marketplace_version}"
    )


HOOKS_DIR = REPO_ROOT / "hooks"

# `python3` on an end user's PATH is whatever the OS ships — 3.9.6 on current
# macOS. Every Python this plugin ships targets requires-python >=3.14 and is
# formatted by black at that target, which emits PEP 758 `except A, B:` — a
# SyntaxError on anything older. So no shipped surface may reach for the system
# interpreter; they all go through bin/mente-python, which decides.
# Only `python3` is flagged. The uv form ends in a bare `python`, and the word
# on its own is ordinary prose ("Target : python / uv-nobuild"); `python3` is
# never anything but a reach for the system binary.
SYSTEM_PYTHON = re.compile(r"(?<![\w./-])python3(?![\w.-])")

# Naming `uv` at a call site is its own drift: it hardcodes half a decision
# (prefer uv) while leaving the other half -- what to do when uv is absent --
# unwritten, which is how nine surfaces ended up each assuming uv was installed.
# bin/mente-python holds the whole order (uv, then a new-enough system
# interpreter, then a diagnosis), so shipped surfaces name the launcher and
# nothing else. It is the only file permitted to say `uv`.
LAUNCHER = REPO_ROOT / "bin" / "mente-python"
DIRECT_UV = re.compile(r"(?<![\w./-])uv run(?![\w.-])")
MINIMUM_PYTHON = tomllib.loads(PYPROJECT.read_text())["project"][
    "requires-python"
].lstrip(">=~^ ")


def _shipped_invocation_surfaces():
    """This plugin's own entry points: the skills the agent runs, the hook
    declarations Claude Code runs, and the eval assertions that grade whether a
    skill ran the engine correctly. The evals belong here because they name OUR
    commands -- an eval still asserting a bare `python3` would grade a correct
    skill as wrong, and quietly re-teach the banned form to whoever reads it
    next. Reference material describing other people's projects stays out.

    Deliberately NOT the whole story: see _agent_instruction_surfaces."""
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        if "-workspace/" in str(skill_file.relative_to(REPO_ROOT)):
            continue
        yield skill_file
    yield from sorted(HOOKS_DIR.glob("*.json"))
    yield from sorted((REPO_ROOT / "evals").glob("*.json"))


def _agent_instruction_surfaces():
    """Subagent briefs under skills/*/agents/. These run Python too, so the
    system-interpreter ban applies -- but the launcher requirement does not.

    The distinction is real rather than an exemption of convenience. An entry
    point runs THIS plugin's code and must not adopt whatever project the
    session happens to sit in, which is why the launcher passes --no-project.
    The mutation gate these briefs invoke is the opposite case: it runs against
    the operator's repository and needs that repository's test environment, so
    project-mode `uv run` is the correct call and routing it through the
    launcher would break it. Two different jobs, two different guards."""
    for agent_brief in sorted(SKILLS_DIR.rglob("agents/*.md")):
        if "-workspace/" in str(agent_brief.relative_to(REPO_ROOT)):
            continue
        yield agent_brief


def test_no_shipped_surface_invokes_the_system_interpreter():
    """Applies to agent briefs as well as entry points: whichever uv mode is
    correct for a call site, reaching past uv to the OS interpreter never is."""
    offenders = []
    for surface in [*_shipped_invocation_surfaces(), *_agent_instruction_surfaces()]:
        for number, line in enumerate(surface.read_text().splitlines(), start=1):
            if SYSTEM_PYTHON.search(line):
                offenders.append(
                    f"{surface.relative_to(REPO_ROOT)}:{number}: {line.strip()}"
                )
    assert not offenders, (
        "Shipped surfaces reaching for the system interpreter — run "
        f"`sh {LAUNCHER.relative_to(REPO_ROOT)} ...` instead:\n" + "\n".join(offenders)
    )


def test_no_shipped_surface_calls_uv_directly():
    """Every shipped surface goes through the launcher, so the fallback exists
    exactly once. A surface that says `uv run` itself has silently opted out of
    the uv-absent branch: on a machine without uv it fails with `command not
    found` instead of the message telling the operator to install it."""
    offenders = []
    for surface in _shipped_invocation_surfaces():
        for number, line in enumerate(surface.read_text().splitlines(), start=1):
            if DIRECT_UV.search(line):
                offenders.append(
                    f"{surface.relative_to(REPO_ROOT)}:{number}: {line.strip()}"
                )
    assert not offenders, (
        f"Direct uv invocations — run `sh {LAUNCHER.relative_to(REPO_ROOT)} ...` "
        "so the uv-absent fallback applies:\n" + "\n".join(offenders)
    )


def test_the_launcher_is_git_tracked():
    """Existing on disk is not shipping. Every other check in this file reads
    the working tree, so an untracked launcher passes them all while the commit
    that references it from hooks.json and three skills goes out without it --
    breaking every Python entry point for anyone who installs after that push.
    `git add -u` would not have caught this: it stages modifications, not new
    files."""
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(LAUNCHER.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert tracked.returncode == 0, (
        f"{LAUNCHER.relative_to(REPO_ROOT)} is not tracked by git — "
        "run `git add` before committing, or it ships broken"
    )


def test_the_launcher_prefers_uv_then_falls_back_then_diagnoses():
    """The three branches the call sites delegate to. Asserted here because a
    launcher that lost its fallback would still pass every other test in this
    file — the surfaces would look correct while the behaviour they delegate to
    had quietly gone missing."""
    launcher_text = LAUNCHER.read_text()
    # The comments explain why the pin is absent, so the flag is only a
    # violation where the shell would actually act on it.
    executable_lines = "\n".join(
        line
        for line in launcher_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    assert "command -v uv" in executable_lines, "uv must be tried first"
    assert (
        "exec uv run --no-project python" in executable_lines
    ), "the uv branch must not pin a version — the operator's own pin decides"
    assert (
        "--python" not in executable_lines
    ), "pinning here would override the operator's deliberate pin"
    assert "uv not found" in executable_lines, "the fallback must nudge toward uv"
    assert (
        f'MINIMUM_VERSION="{MINIMUM_PYTHON}"' in executable_lines
    ), "the launcher's floor must track requires-python, not drift from it"


def _shipped_python_modules():
    """Every Python module this plugin ships to a user's machine. Excludes the
    test suite, which only ever runs under uv here."""
    for directory in (HOOKS_DIR, REPO_ROOT / "scripts", SKILLS_DIR):
        for module in sorted(directory.rglob("*.py")):
            relative = str(module.relative_to(REPO_ROOT))
            if "-workspace/" in relative or "__pycache__" in relative:
                continue
            yield module


def test_no_shipped_module_carries_a_shebang():
    """A `#!/usr/bin/env python3` line is a promise the module cannot keep: none
    of these carry the exec bit, and black formats them at py314, whose syntax
    the OS interpreter rejects outright. They are launched through uv or not at
    all, so the shebang can only mislead."""
    offenders = [
        str(module.relative_to(REPO_ROOT))
        for module in _shipped_python_modules()
        if module.read_text().startswith("#!")
    ]
    assert not offenders, "Shipped modules with a shebang:\n" + "\n".join(offenders)


OVERLAP_MAP = DOCS_DIR / "lens-overlap.md"


def test_overlap_map_covers_all_23_patterns():
    text = OVERLAP_MAP.read_text()
    missing = [pattern for pattern in GOF_PATTERNS if pattern not in text]
    assert not missing, f"overlap map missing patterns: {missing}"


PATTERNS_MD = SKILLS_DIR / "gof" / "references" / "patterns.md"
REQUIRED_PATTERN_SUBSECTIONS = (
    "**Intent**",
    "**Detect by**",
    "**Grade A**",
    "**Grade C/D issues**",
    "**Suggest when**",
    "**Don't suggest when**",
)


def _pattern_blocks(text):
    """Map each '### <pattern>' heading to the text of its block (up to the next heading)."""
    blocks = {}
    current_name = None
    current_lines = []
    for line in text.splitlines():
        heading = re.match(r"^###\s+(.*\S)\s*$", line)
        if heading:
            if current_name is not None:
                blocks[current_name] = "\n".join(current_lines)
            current_name = heading.group(1)
            current_lines = []
        elif re.match(r"^##\s", line):  # a category header closes the current block
            if current_name is not None:
                blocks[current_name] = "\n".join(current_lines)
                current_name = None
                current_lines = []
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        blocks[current_name] = "\n".join(current_lines)
    return blocks


def test_patterns_md_has_all_23_with_required_subsections():
    blocks = _pattern_blocks(PATTERNS_MD.read_text())
    missing_patterns = [pattern for pattern in GOF_PATTERNS if pattern not in blocks]
    assert not missing_patterns, f"patterns.md missing: {missing_patterns}"
    incomplete = []
    for pattern in GOF_PATTERNS:
        for subsection in REQUIRED_PATTERN_SUBSECTIONS:
            if subsection not in blocks[pattern]:
                incomplete.append(f"{pattern}: missing {subsection}")
    assert not incomplete, "patterns.md incomplete:\n" + "\n".join(incomplete)


def test_patterns_md_defines_shared_rubrics():
    text = PATTERNS_MD.read_text()
    for required_block in ("## Grade rubric", "## Tier rubric", "## Risk rubric"):
        assert required_block in text, f"patterns.md missing '{required_block}'"


GOF_EVALS = REPO_ROOT / "evals" / "gof-evals.json"
EVAL_CASE_KEYS = {"id", "skill", "prompt", "expected_output", "assertions"}


def test_gof_evals_valid_schema():
    data = json.loads(GOF_EVALS.read_text())
    assert data["skill_name"] == "gof"
    assert isinstance(data["evals"], list) and data["evals"], "no eval cases"
    for eval_case in data["evals"]:
        assert (
            eval_case.keys() >= EVAL_CASE_KEYS
        ), f"case {eval_case.get('id')} missing keys"
        assert isinstance(eval_case["assertions"], list) and eval_case["assertions"]
