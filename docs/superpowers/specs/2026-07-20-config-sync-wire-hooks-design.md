# config-sync wire-hooks — design

> Tracks the provisioning half of #65, split out as #68. The portability half
> (`config_sync_roots`, `${TOKEN}` rewrite of hook command paths) shipped in #67
> and is a hard dependency of this design.

## 1. Problem

config-sync **propagates** the `settings.json` `hooks` block across machines
(union merge on import), but it never **provisions** the first registration. When
a repo ships a hook script (e.g. `mente-apex-memory/hooks/protect_brain.py`), that
script only runs once a human has hand-edited `~/.claude/settings.json` on some
machine. A fresh machine, or a newly-added hook, has no way to converge to "the
hooks this setup expects" the way plugins already converge via the desired-state
manifest (`config_sync_plugins.py`).

**Reality check (2026-07-20):** no hook is owned by the mente-apex *plugin* today.
The hooks in play are all external — `protect_brain.py` / `enforce_gates.py` live
in the `mente-apex-memory` repo (not a Claude plugin), and `brand-deliverable-guard.sh`
is a personal `~/.claude/hooks/` script. So the "make plugin-owned hooks native"
path has no current subjects; this design is purely about provisioning
**declared, repo-shipped hooks** onto a machine that lacks them.

Native Claude Code plugin hooks (`hooks/hooks.json` + `${CLAUDE_PLUGIN_ROOT}`,
auto-registered on enable) remain the preferred answer for any hook the plugin
itself authors in future — and this design stays compatible with that format so
nothing is wasted if a source repo later becomes a plugin.

## 2. Shape of the solution

A hook can't declare *when* it should run from a bare script path, so each source
that ships hooks includes a small declaration file. config-sync discovers those
declarations under the roots it already knows (#67), diffs them against the live
`settings.json`, and — behind the same one-confirmation gate as `plugins-apply` —
registers any missing ones, written in portable `${TOKEN}` form.

Two engine commands mirror the plugins channel exactly:

- `hooks-plan <repo>` — pure query: prints the actions it *would* take (register
  which hooks), plus skipped-with-reason. No writes.
- `hooks-apply <repo>` — runs the plan through a gated executor that writes the
  registrations into local `settings.json`. Idempotent; re-running is a no-op.

The conceptual user-facing name is **wire-hooks**; the `/config-sync` skill runs
plan → show → (consent) → apply, the way it already does for plugins.

## 3. Hook declaration format & discovery

**Format — native-compatible.** A source ships `hooks/hooks.json` whose body is a
`hooks` block identical in shape to the one in `settings.json` and to Claude Code's
native plugin hooks:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          { "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/protect_brain.py",
            "timeout": 10 }
        ]
      }
    ]
  }
}
```

`${CLAUDE_PLUGIN_ROOT}` is the placeholder meaning "the root this declaration was
found under." If the source ever becomes a real plugin, Claude Code sets that var
itself and reads the same file directly — config-sync simply stops needing to wire
it. For the non-plugin case, config-sync substitutes the discovering root's
`${TOKEN}` (see §5).

**Discovery.** config-sync scans each **named** root from `config_sync_roots`
(the `CONFIG_SYNC_ROOT_*` declarations — *not* the HOME catch-all, which is a
portability root, not a hook source) for `<root>/hooks/hooks.json`. The mente-apex
plugin's own root is also scanned when present, so plugin-authored declarations
work later with no new code. Malformed or missing files are skipped, never fatal.

## 4. New unit — `scripts/config_sync_hooks.py`

Mirrors `config_sync_plugins.py` (pure planner + gated executor + injected host),
so the two channels read the same and neither uses module globals.

```
@dataclass(frozen=True)
class DeclaredHook:
    hook_id: str        # short stable hash (12 hex) of (root_token, event, matcher,
                        # tokenised command) — computed BEFORE the marker is appended
    event: str          # PreToolUse | PostToolUse | ...
    matcher: str
    command: str        # already tokenised (${TOKEN}/...), ready for settings.json
    timeout: int | None

@dataclass
class HookAction:        # verb is always "register" (union-only; never unregisters)
    verb: str
    hook_id: str
    detail: dict

@dataclass
class HookPlan:
    actions: list        # list[HookAction]
    skipped: list        # human-readable reasons

def plan_hook_wiring(roots, settings_reader) -> HookPlan: ...
def execute_hook_plan(plan, settings_writer) -> HookResult: ...
```

- `roots` is a `config_sync_roots.RootRegistry` (already the composition seam).
- `settings_reader` / `settings_writer` is an injected host (Protocol) that reads
  and writes `~/.claude/settings.json`; production wiring uses the real file, tests
  pass a fake. DIP, no globals — same as `PluginRegistryReader` / `PluginInstaller`.
- The planner is pure: discover declarations → resolve each command to `${TOKEN}`
  form → assign `hook_id` → diff against already-registered marked hooks → emit a
  `register` action per missing hook. Never emits an unregister.

## 5. Identity, idempotency & safety

**Marker.** Every hook config-sync registers gets a trailing marker appended to its
command string: `… # config-sync:<hook_id>` (e.g. `# config-sync:ab12cd34ef56`).
The `hook_id` is a short hash of the clean (pre-marker) declaration, so appending
the marker never feeds back into the identity. This is:

- schema-safe (no extra JSON keys the settings schema might reject),
- shell-safe (a trailing `#` comment is ignored by the shell that runs the hook),
- and invisible to #67's path rewriter (it only rewrites path prefixes).

**Idempotency.** `plan_hook_wiring` treats a declared hook as already-present iff
`settings.json` contains a hook whose command carries `# config-sync:<hook_id>`.
Present → skipped; missing → `register`. Re-running after an apply yields an empty
plan.

**Never clobber hand-added hooks.** config-sync only ever *adds* marked hooks and
only ever recognises marked hooks as "its own." A hook a human added by hand (no
marker) is never matched, moved, or removed — even if it points at the same script.
Union-only, consistent with the rest of config-sync.

**Command-token resolution.** `${CLAUDE_PLUGIN_ROOT}` in a declaration is rewritten
to the discovering root's token (e.g. `${MENTE_APEX_MEMORY}`) at plan time, so the
stored registration is portable by construction. On apply and on every later
import, `config_sync_roots.localize` expands it to the local absolute path (#67).
A HOME-rooted declaration stores `${HOME}/…`, valid on every machine with no env
var needed.

## 6. CLI + skill workflow

- `scripts/config_sync.py`: add `hooks-plan` and `hooks-apply` to `COMMANDS`, each
  taking a repo path, each a thin wrapper that builds `_root_registry()` + the real
  settings host and calls into `config_sync_hooks`. Output is JSON (actions/skipped
  for plan; outcomes/skipped for apply), matching `plugins-plan`/`plugins-apply`.
- `/config-sync` skill: after the plugins step, run `hooks-plan`; if it has actions,
  show them and ask once; on yes, run `hooks-apply`. Purely additive to the flow.
- `/config-sync-setup` skill: mention wire-hooks as part of first-machine setup.

## 7. Out-of-repo change — the memory repo declaration

For the memory hooks to be wired, `mente-apex-memory` gains a small
`hooks/hooks.json` declaring `protect_brain.py` and `enforce_gates.py` (the two
scripts already there). This is the only change outside this repo; it is additive
and native-compatible. Flagged explicitly because it touches a second repo — done
only with the user's go-ahead.

## 8. Testing (TDD, `.venv/bin/python -m pytest`)

Unit — `tests/test_hook_wiring.py`:
- discovery reads a well-formed `hooks/hooks.json` under a named root; ignores a
  malformed / missing one without error;
- `${CLAUDE_PLUGIN_ROOT}` resolves to the discovering root's token;
- planner emits `register` for a declared hook absent from settings;
- planner skips a declared hook already present (marker match) → empty plan =
  idempotent;
- a hand-added (unmarked) hook for the same script is left untouched;
- `execute_hook_plan` writes the marked, tokenised registration into the fake host;
- round-trip: a wired hook survives export→import portably (integration with #67).

CLI — `tests/test_hooks_cli.py`: `hooks-plan` prints actions without writing;
`hooks-apply` writes and is a no-op on second run.

## 9. Delivery

- Branch `feat/config-sync-wire-hooks` (already created off `main`).
- Python 3.14 stdlib only; engine files import nothing third-party.
- Commit per TDD cycle; PR body closes #68. The memory-repo `hooks.json` ships as a
  separate small change in that repo, not in this PR.

## 10. Scope — what this does NOT do

- Does **not** unregister or prune hooks (union-only, like snapshot import).
- Does **not** touch hand-added or supacode-managed hooks.
- Does **not** repackage `mente-apex-memory` as a plugin (future option).
- Does **not** invent hooks or change what any hook does.

## 11. Open questions carried to planning

1. Should `hooks-apply` also *update* a marked hook whose declaration changed
   (e.g. matcher edited), or only add missing ones? Leaning: update-in-place for
   marked hooks (safe, since we own them), but MVP could add-only. Decide in plan.
2. Surface wire-hooks automatically in `/config-sync`, or keep it an explicit
   opt-in command for the first release? Leaning: show the plan automatically but
   never apply without consent.
