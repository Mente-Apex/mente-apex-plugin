"""One worktree per lens, cut at the ref actually under review (issue #156).

The Agent tool's `isolation: "worktree"` takes no ref, so a plugin cannot say
where the harness cuts one -- and in the reported run it cut at the branch's
merge-base, which contains none of the branch's commits. Five analyzers
re-resolved their scoped files against the orchestrator's checkout and audited
that from inside their sandbox; the sixth, whose gate has to execute the code,
reported nothing. The audit looked complete with one lens reduced to zero.

So the orchestrator makes the worktrees itself, here, where the ref is an
argument and the result is **verified** rather than hoped for. A worktree at the
wrong ref stops being something a downstream agent has to notice: this module
refuses to hand one over.

Mechanical rather than advisory, deliberately (issue #124). "Tell the
orchestrator to run `git worktree add`" is a guard nothing can check, six times
per audit, in the one place where a mistake is invisible to everyone
downstream.

**Detached, always.** Git refuses to check out one branch in two worktrees, so
six lenses sharing a branch is not a preference to weigh -- `--detach` is the
only shape that works at all.

**All-or-nothing.** A half-built set is worse than none: the lenses that got a
worktree audit the branch, the ones that did not audit whatever the fallback
finds, and the consolidated report merges both without knowing. A failed create
therefore removes what it already made before raising.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Bounded like every other subprocess this plugin starts. Worktree plumbing is
# local and quick, or it is stuck on a lock some crashed process still holds --
# and a hang here strands the whole audit before a single lens has run.
GIT_TIMEOUT_SECONDS = 120


class WorktreeSetupError(RuntimeError):
    """The requested worktree set could not be created, or not verified."""


def _run_git(repo_root, *arguments):
    """Run one git command in `repo_root`.

    Injected everywhere below rather than called directly, so a test can
    substitute a fake without a repository and so the timeout policy lives in
    exactly one place.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorktreeSetupError(
            f"git {' '.join(arguments)} did not finish within "
            f"{GIT_TIMEOUT_SECONDS}s in {repo_root}"
        ) from exc
    except OSError as exc:
        # git missing from PATH, repo_root gone, undecodable output. Without this
        # the exception escaped `main`, which catches only WorktreeSetupError, so
        # the orchestrator parsed empty stdout, got no {"error": ...}, and the
        # audit proceeded with no worktrees -- the invisible failure this module
        # exists to refuse. `mutation_gate_baseline` converts OSError for the
        # same reason.
        raise WorktreeSetupError(
            f"could not run git {' '.join(arguments)} in {repo_root}: {exc}"
        ) from exc


def resolve_ref(repo_root, ref, run_git=_run_git):
    """The commit `ref` names, as a full SHA.

    Resolved once, up front, for two reasons: a ref that does not exist should
    fail before any worktree is created rather than half way through, and the
    SHA is what every created worktree is then checked against. Comparing
    against a resolved commit is exact; comparing against the ref name would
    pass for a worktree cut at a different commit the name later moved to.
    """
    result = run_git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if result.returncode != 0:
        raise WorktreeSetupError(
            f"cannot resolve {ref!r} in {repo_root}, so there is no ref to cut "
            f"worktrees at: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _head_of(worktree, run_git):
    result = run_git(worktree, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


def create_worktrees(repo_root, ref, names, root=None, run_git=_run_git):
    """One detached worktree per name, all at `ref`, verified before returning.

    Returns `(root, {name: path}, commit)` -- the commit included so a caller
    reports the SHA that was actually verified rather than resolving the ref again.
    `root` is a fresh temp directory unless one
    is given -- outside the repository either way, because a worktree nested
    inside the tree it was cut from is a tree that contains itself and every
    file walk downstream doubles.

    The verification is the point of this function. `git worktree add` can
    report success and still leave a checkout at a commit other than the one
    asked for (a ref that moved mid-run, a plugin or hook rewriting HEAD), and
    that failure is invisible to the agent handed the path -- it just sees code
    that does not match the branch. Every worktree's HEAD is compared against
    the resolved SHA here, and a mismatch tears the whole set down.
    """
    # Absolute from here down, both of them. `git worktree add` resolves a
    # relative destination against `git -C <repo_root>`, while `_head_of` ran
    # `git -C <destination>` against the PROCESS cwd -- so with a relative
    # --repo-root the verifier checked a directory that did not exist, and a
    # correctly-created set was torn down with this module's own #156 alarm about
    # a defect that had not occurred. The payload also hands `root` back to
    # `remove`, possibly from a different cwd.
    repo_root = Path(repo_root).resolve()
    commit = resolve_ref(repo_root, ref, run_git)
    root = (
        Path(tempfile.mkdtemp(prefix="lens-worktrees-"))
        if root is None
        else Path(root).resolve()
    )
    root.mkdir(parents=True, exist_ok=True)

    created = {}
    try:
        for name in names:
            destination = root / name
            result = run_git(
                repo_root, "worktree", "add", "--detach", "-q", str(destination), commit
            )
            if result.returncode != 0:
                raise WorktreeSetupError(
                    f"could not create the {name} worktree at {commit[:12]} in "
                    f"{destination}: {result.stderr.strip()}"
                )
            created[name] = destination
            actual = _head_of(destination, run_git)
            if actual != commit:
                raise WorktreeSetupError(
                    f"the {name} worktree is at {actual[:12] or 'an unreadable HEAD'}, "
                    f"not the requested {commit[:12]} -- this is the defect the "
                    "whole module exists to prevent (issue #156), so the set is "
                    "refused rather than handed over"
                )
    except BaseException:
        # Partial sets are worse than none: some lenses would audit the branch
        # and some whatever their fallback found, and the consolidated report
        # would merge both without knowing which was which.
        remove_worktrees(repo_root, created.values(), run_git=run_git)
        raise
    return root, created, commit


def remove_worktrees(repo_root, paths, run_git=_run_git):
    """Unregister each worktree, reporting failures rather than raising.

    Teardown runs after the audit's results already exist, so a failure here
    must not replace them with an exception -- the same rule the mutation
    gate's workspace teardown follows. Returns `[(path, error), ...]` for
    whatever could not be removed, so a caller can say so instead of leaving a
    stale entry registered against the operator's repo in silence.
    """
    failures = []
    for path in paths:
        try:
            result = run_git(repo_root, "worktree", "remove", "--force", str(path))
        except WorktreeSetupError as exc:
            failures.append((str(path), str(exc)))
            continue
        if result.returncode != 0:
            failures.append((str(path), result.stderr.strip()))
    return failures


def _create_command(arguments):
    root, created, commit = create_worktrees(
        arguments.repo_root, arguments.ref, arguments.lenses, root=arguments.root
    )
    return {
        "ref": arguments.ref,
        # The commit that was VERIFIED, returned by the creation itself. Resolving
        # the ref a second time here could report a different SHA than the one the
        # worktrees were checked against, if the ref moved in between -- which is
        # precisely the drift this module exists to detect.
        "commit": commit,
        "root": str(root),
        "worktrees": {name: str(path) for name, path in created.items()},
    }


def _remove_command(arguments):
    paths = [Path(arguments.root) / name for name in arguments.lenses]
    failures = remove_worktrees(arguments.repo_root, paths)
    return {
        "removed": [str(path) for path in paths if str(path) not in dict(failures)],
        "failures": [{"path": path, "error": error} for path, error in failures],
    }


def main(argv=None):
    """Create or remove a lens worktree set, printing JSON either way.

    JSON because the caller is an orchestrator agent that has to hand each path
    to a subagent brief: a human-readable table would have to be re-parsed by
    the one reader least able to do it reliably.
    """
    parser = argparse.ArgumentParser(
        description="Create or remove one worktree per lens, at a named ref."
    )
    parser.add_argument("command", choices=("create", "remove"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--ref",
        default="HEAD",
        help=(
            "The ref to cut every worktree at — the branch under review, not "
            "its merge-base. Verified after creation; a mismatch refuses the "
            "whole set."
        ),
    )
    parser.add_argument("--lenses", nargs="+", required=True)
    parser.add_argument(
        "--root",
        default=None,
        help="Directory to hold the worktrees (a fresh temp dir by default). "
        "Required for `remove`.",
    )
    arguments = parser.parse_args(argv)

    if arguments.command == "remove" and arguments.root is None:
        parser.error("--root is required to remove a worktree set")

    try:
        payload = (
            _create_command(arguments)
            if arguments.command == "create"
            else _remove_command(arguments)
        )
    except WorktreeSetupError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps(payload, indent=2))
    return 1 if payload.get("failures") else 0


if __name__ == "__main__":
    import lens_worktrees

    sys.exit(lens_worktrees.main())
