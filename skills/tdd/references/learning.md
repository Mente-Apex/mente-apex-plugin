# Learning and Adaptation

TDD workflows are shaped by the project they live in. Lessons from a session should
outlive the session — but they go to the Mente Apex memory brain, not to ad-hoc files.

## What to watch for during the cycle

- **Fixtures that keep getting rebuilt** — the same setup appearing across test files
  belongs in `conftest.py`; the *pattern* belongs in memory so future sessions start
  there.
- **Recurring design smells** — a god class every feature touches, a violation that
  resurfaces each cycle. Don't fix it mid-cycle; note it and suggest a `/solid` audit
  as separate work.
- **Patterns that work for this codebase** — builder functions for test data, a
  particular integration-test structure, an assertion style the team prefers.
- **Dependencies and quirks** — rate limits on external services, slow suites needing
  markers, database fixtures with special teardown.

## Where lessons go — detect a backend, degrade gracefully

*Persisting* the lesson matters more than *where*. Resolve a backend by what's actually
present, so the skill behaves the same in a bare public checkout as in a fully-wired
Mente Apex environment — nothing here requires an external memory system. In priority
order:

1. **A committed `memory/` dir in the repo**, if the project keeps one (an in-repo
   technical-knowledge tier) — test conventions for that project belong there. Portable:
   it travels with the repo, no external tool needed.
2. **The Mente Apex brain, when detected** — if `mem` is on PATH or the
   `mente-apex-memory` MCP is available, capture with
   `mem capture "…" --kind <semantic|episodic|procedural> --scope project --project <slug>
   --tags <convention|decision|gotcha>` (or the MCP capture tool). `--kind` is the
   *memory type*, not the lesson label — a convention/gotcha is usually `semantic`, a
   dated decision `episodic`, a how-to `procedural`; "convention/decision/gotcha" are
   `--tags` (passing them to `--kind` is rejected). Treat this as an *enhancement used
   when present*, never a prerequisite.
3. **Neither present** — propose a short `docs/testing-conventions.md` in the repo so the
   knowledge isn't lost. This is the always-works default; never assume a brain exists.

## Never capture silently

Propose the capture and let the user approve: *"I noticed [pattern]. Want me to capture
this so future sessions start with it?"* The user owns the brain. In programmatic mode,
don't write memory at all — list suggested captures in your final report and let the
calling context decide.
