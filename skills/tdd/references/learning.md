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

## Where lessons go

- **Durable lessons** (conventions, decisions, gotchas): capture into the brain with
  `mem capture "…" --kind <semantic|episodic|procedural> --scope project --project <slug>
  --tags <convention|decision|gotcha>`, or the `mente-apex-memory` MCP capture tool when
  available. `--kind` is the *memory type*, not the lesson label: a convention or gotcha
  is usually `semantic`, a dated decision `episodic`, a how-to `procedural` — and
  "convention/decision/gotcha" are `--tags`. (Passing them to `--kind` is rejected.)
- **Project-tier knowledge in customer repos**: if the repo has a committed `memory/`
  directory (the brain's in-repo technical tier, ingested via `projects.toml`), test
  conventions for that project belong there.
- **No brain on this machine**: fall back to suggesting a short
  `docs/testing-conventions.md` in the repo so the knowledge isn't lost.

## Never capture silently

Propose the capture and let the user approve: *"I noticed [pattern]. Want me to capture
this so future sessions start with it?"* The user owns the brain. In programmatic mode,
don't write memory at all — list suggested captures in your final report and let the
calling context decide.
