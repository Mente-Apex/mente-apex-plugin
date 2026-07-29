"""Which files a mutation run covers.

Resolving a scope ("merge-base", "working-tree", "full") to a set of paths is
a git question, not a mutation-dispatch one, so it lives apart from the gate.
"""

import subprocess


def _git(repo_root, *args, check=True):
    """Run git and return stdout.

    `check=True` raises on failure, but a bare `CalledProcessError` does not
    surface stderr -- an operator sees only an exit code and has to go
    reproduce the command by hand to find out whether it was an unborn
    branch, a shallow clone, or something else entirely. Re-raising with
    stderr attached names the actual cause in the message the operator
    already sees.
    """
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True
    )
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
        paths.append(path)
        index += 2 if status[0] in ("R", "C") else 1
    return paths


def changed_paths(repo_root, scope="merge-base"):
    """The files this run mutates.

    merge-base is the default because it is stable: an operator committing
    mid-audit should not change what the sweep covers. Full-repo mutation is
    far too slow to be anyone's default in an interactive skill.

    Every git call here uses `-z` (NUL-separated, unquoted output) rather
    than the default newline/quoted format: a default-porcelain rename shows
    up as "old -> new" and a path containing a space gets shell-quoted, and
    naive line-splitting turned both into a bogus string that resolves to no
    file on disk.
    """
    if scope == "merge-base":
        base = _default_branch(repo_root)
        fork_point = _git(repo_root, "merge-base", base, "HEAD").strip()
        output = _git(repo_root, "diff", "--name-only", "-z", fork_point, "HEAD")
        paths = [path for path in output.split("\0") if path]
    elif scope == "working-tree":
        output = _git(repo_root, "status", "--porcelain", "-z", "--untracked-files=all")
        paths = _parse_status_z(output)
    elif scope == "full":
        output = _git(repo_root, "ls-files", "-z")
        paths = [path for path in output.split("\0") if path]
    else:
        raise ValueError(f"unknown scope: {scope!r}")
    return tuple(paths)
