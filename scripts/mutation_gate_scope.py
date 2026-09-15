"""Which files a mutation run covers.

Resolving a scope ("merge-base", "working-tree", "full") to a set of paths is
a git question, not a mutation-dispatch one, so it lives apart from the gate.
"""

import subprocess

# Bounded, like every other subprocess the gate starts. These are plumbing
# queries against a local repo, so they are quick or they are stuck -- a git
# call waiting on a lock held by a crashed process would otherwise hang the
# gate before it had resolved a single path.
GIT_TIMEOUT_SECONDS = 120


def _git(repo_root, *args, check=True):
    """Run git and return stdout.

    `check=True` raises on failure, but a bare `CalledProcessError` does not
    surface stderr -- an operator sees only an exit code and has to go
    reproduce the command by hand to find out whether it was an unborn
    branch, a shallow clone, or something else entirely. Re-raising with
    stderr attached names the actual cause in the message the operator
    already sees. A timeout is raised the same way rather than left to
    surface as a bare `TimeoutExpired` with no indication of which call hung.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"git {' '.join(args)} did not finish within "
            f"{GIT_TIMEOUT_SECONDS}s in {repo_root}"
        ) from exc
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo_root} "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _default_branch(repo_root):
    """The repo's actual default branch, determined rather than guessed.

    main and master cover the overwhelming majority of repos and are checked
    first. Failing that, ask git what it actually knows: the remote's
    advertised HEAD, then a configured `init.defaultBranch` that matches a
    real local branch. Guessing the alphabetically-first local branch (what
    `git branch --format=...` returns) would silently pick the wrong fork
    point in a repo whose default is e.g. `develop` -- possibly `aardvark` --
    so where none of these resolves to a real branch, this fails loudly
    instead of guessing.
    """
    branches = _git(repo_root, "branch", "--format=%(refname:short)").split()
    for candidate in ("main", "master"):
        if candidate in branches:
            return candidate

    origin_head = _git(
        repo_root,
        "symbolic-ref",
        "-q",
        "--short",
        "refs/remotes/origin/HEAD",
        check=False,
    ).strip()
    if origin_head.startswith("origin/"):
        candidate = origin_head.removeprefix("origin/")
        if candidate in branches:
            return candidate

    configured = _git(
        repo_root, "config", "--get", "init.defaultBranch", check=False
    ).strip()
    if configured in branches:
        return configured

    raise ValueError(
        "cannot determine the default branch: no 'main' or 'master', no "
        "origin/HEAD, and no usable init.defaultBranch "
        f"(local branches: {branches!r})"
    )


def _parse_status_z(output):
    """Parse `git status --porcelain -z` into the paths that exist on disk.

    NUL-separated and unquoted, unlike the default porcelain format -- a
    filename containing a space parses correctly instead of leaving literal
    quote characters in the string. A rename or copy record supplies the new
    path followed by the old path as a second NUL-terminated field; the old
    path no longer exists on disk, so only the new path is kept.

    A deleted path is dropped for the same reason, and was not: `git rm a.py`
    put `a.py` into the selection, where it became a `source_paths` entry
    naming a file absent from the workspace and broke the whole Python
    partition over a change that had nothing to mutate. Deletion shows in
    either status column -- `D ` staged, ` D` in the worktree -- so both are
    checked.
    """
    tokens = output.split("\0")
    paths = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token:
            index += 1
            continue
        status, path = token[:2], token[3:]
        renamed_or_copied = status[0] in ("R", "C")
        if "D" not in status:
            paths.append(path)
        index += 2 if renamed_or_copied else 1
    return paths


def changed_paths(repo_root, scope="merge-base", pathspec=()):
    """The files this run mutates.

    merge-base is the default because it is stable: an operator committing
    mid-audit should not change what the sweep covers. Full-repo mutation is
    far too slow to be anyone's default in an interactive skill.

    `pathspec` narrows whichever scope was asked for to a named subtree, and
    exists for the case the two above leave unreachable: a stand-alone audit of
    an untouched tree, where merge-base resolves to an empty diff and the sweep
    covers nothing at all. `--scope full` reaches those files but costs a
    whole-repo mutation run; `--scope full --paths tests/orders` reaches the
    part the audit is actually about at a cost the operator chose. It is passed
    to git verbatim after a `--` separator, so every scope narrows the same way
    rather than one of them growing a special case, and an empty pathspec (the
    default) leaves each query exactly as it was.

    Every git call here uses `-z` (NUL-separated, unquoted output) rather
    than the default newline/quoted format: a default-porcelain rename shows
    up as "old -> new" and a path containing a space gets shell-quoted, and
    naive line-splitting turned both into a bogus string that resolves to no
    file on disk.

    A deleted file is never selected. `--diff-filter=d` (lowercase: exclude
    deletions) drops it here, and `_parse_status_z` drops it for the
    working-tree scope. A path that no longer exists cannot be mutated, and
    handing one to a backend as though it could poisons the run for every
    other file in the same partition.
    """
    # Only ever appended when non-empty: a bare trailing `--` is harmless to
    # git but says "no pathspec" in a way that reads, in a logged command line,
    # exactly like a narrowing that selected nothing.
    limit = ["--", *pathspec] if pathspec else []

    if scope == "merge-base":
        base = _default_branch(repo_root)
        fork_point = _git(repo_root, "merge-base", base, "HEAD").strip()
        output = _git(
            repo_root,
            "diff",
            "--name-only",
            "--diff-filter=d",
            "-z",
            fork_point,
            "HEAD",
            *limit,
        )
        paths = [path for path in output.split("\0") if path]
    elif scope == "working-tree":
        output = _git(
            repo_root,
            "status",
            "--porcelain",
            "-z",
            "--untracked-files=all",
            *limit,
        )
        paths = _parse_status_z(output)
    elif scope == "full":
        output = _git(repo_root, "ls-files", "-z", *limit)
        paths = [path for path in output.split("\0") if path]
    else:
        raise ValueError(f"unknown scope: {scope!r}")
    return tuple(paths)


def empty_scope_advice(scope, pathspec=()):
    """What an empty selection MEANS for this scope, and what to do about it.

    An empty selection is not a failure -- nothing broke, so it stays exit 0
    and stays out of `unverified_reasons`. But "0 files selected" reads like a
    finished sweep, and at `merge-base` on an untouched tree it is the OPPOSITE
    of one: the scope the skill advertises as catching born-vacuous tests
    cannot see a single one, because a stand-alone audit has no diff (issue
    #149). The remedy exists (`--scope full --paths <subtree>`); what was
    missing is the gate saying so at the moment an operator is looking at zero.

    It lives here rather than in the reporter because it is a fact about what a
    scope MEANS, and this module owns scope semantics -- the reporter only
    renders what it is handed. A new scope therefore extends this function, and
    the renderer does not change at all.

    `""` where there is nothing useful to say: a scope already at `full` cannot
    be advised to widen to `full`, and an unrecognised scope gets silence
    rather than invented advice -- `changed_paths` rejects those anyway, and a
    wrong remedy is worse than none.
    """
    if pathspec:
        joined = ", ".join(pathspec)
        return (
            f"the pathspec matched no files ({joined}) -- check the path, or "
            "widen it; a narrowed sweep that selected nothing proves nothing "
            "about the tree it named"
        )
    if scope in ("merge-base", "working-tree"):
        return (
            "this scope covers a diff, and there is none -- expected on a "
            "stand-alone audit of an untouched tree, where it means the sweep "
            "proved nothing rather than finding nothing. Re-run narrowed to "
            "reach it: `--scope full --paths <subtree>` over the "
            "highest-value part of the tree, at a cost you choose"
        )
    if scope == "full":
        return (
            "the whole tree was in scope and no file landed in a stack any "
            "backend claims, so there was nothing this gate could mutate"
        )
    return ""


def scope_label(scope, pathspec=()):
    """How this run's coverage is named in the JSON payload and the report.

    A narrowed run must never read as the scope it narrowed: `full` on a
    hundred-file repo and `full` limited to one test package produce the same
    "No survivors in scope." line, and only one of them earned it. Naming the
    pathspec in the label is what keeps the report honest, and it costs the
    reporter nothing -- `scope` is already a free-form string there.
    """
    if not pathspec:
        return scope
    return f"{scope} (paths: {', '.join(pathspec)})"
