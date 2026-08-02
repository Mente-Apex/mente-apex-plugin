"""Telling a report THIS run wrote from one that was already lying there.

Every backend that reads its results out of a file on disk has the same hole,
and three of the four had it: check that the report exists, find it there, and
parse a *previous* run's results as though they were this run's. The workspace
makes it the normal case rather than a corner one -- `--scope working-tree`
copies the operator's tree verbatim, and every one of these report locations is
gitignored (`reports/`, `mutants/`, `target/`), so a stale report is carried in
by construction. A tool that then dies before writing anything leaves the old
all-killed report sitting exactly where the backend looks for it, and the run
reports a clean pass over code it never mutated.

Existence is therefore never the test. Identity is: record each candidate's
mtime BEFORE the run, and afterwards accept only paths that are new or whose
mtime moved. Comparing identities rather than a timestamp against a captured
clock reading is what keeps it exact -- no filesystem-granularity window for a
stale report to slip through, and no tolerance constant to get wrong.

The policy lives here once; WHERE a backend's reports are found is the
backend's own business and is injected, because that is the only part that
differs between Stryker's fixed `reports/mutation/mutation.json`, mutmut's
`mutants/` cache and PIT's timestamped per-module `target/pit-reports/` tree.
"""


class ReportFreshness:
    """A before/after check that a run actually wrote its report.

    `locate` is injected rather than subclassed: it is a callable taking
    `repo_root` and returning the candidate report paths, so a backend
    contributes its own discovery strategy without this policy knowing
    anything about report formats, and a test substitutes a plain lambda.

    Single use per run, and stateful by design -- `snapshot()` must be called
    before the tool runs and `written_since()` after, so the pairing is
    visible at the call site instead of hidden in a parameter that is easy to
    forget to thread through.
    """

    def __init__(self, locate):
        self._locate = locate
        self._before = {}
        self._snapshot_taken = False

    def snapshot(self, repo_root):
        """Record every candidate report's identity, before the run.

        A path that cannot be stat'd is simply absent from the snapshot, which
        makes it "new" afterwards if it becomes readable -- the safe direction,
        since the alternative would be treating an unreadable file as
        unchanged and accepting whatever it contains.
        """
        self._before = {}
        for path in self._locate(repo_root):
            try:
                self._before[path] = path.stat().st_mtime_ns
            except OSError:
                continue
        self._snapshot_taken = True

    def written_since(self, repo_root):
        """Every report this run actually wrote, newest last.

        ALL of them, not just the newest. A Maven reactor writes one report per
        module, which is exactly what the discovery strategy is built to find;
        returning a single path meant a run over `billing` and `shipping` read
        whichever finished last and silently discarded the other module's
        survivors.
        """
        if not self._snapshot_taken:
            # Without a before-picture every existing report looks new, which
            # is precisely the stale-report bug this class exists to close.
            # One refactor that drops the `snapshot()` call would silently
            # reopen it, so the pairing is enforced rather than assumed.
            raise RuntimeError(
                "written_since() called without snapshot(); with no "
                "before-picture a stale report is indistinguishable from one "
                "this run wrote"
            )
        written = []
        for path in self._locate(repo_root):
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            if self._before.get(path) != mtime:
                written.append((mtime, path))
        return tuple(path for _, path in sorted(written))
