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
                        # SCRIPT KEY) — computed BEFORE the marker is appended.
                        # Revised 2026-08-02 (§11.1): hashing the whole command
                        # made every edit mint a new id and orphan the old entry.
    event: str          # PreToolUse | PostToolUse | ...
    matcher: str
    command: str        # already tokenised (${TOKEN}/...), ready for settings.json
    timeout: int | None
    # A marker written under an older identity scheme is re-found by
    # (event, matcher, script filename) via registrations_by_script(), NOT by
    # carrying the old hash on the declaration — see §11.1.

@dataclass
class HookAction:        # verb is "register" (append) or "update" (rewrite in
                         # place at detail["location"]). Never unregisters —
                         # removal is hooks-prune's job, behind its own gate.
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
  `register` action per missing hook, or an `update` per hook whose registration
  exists but no longer matches. Never emits an unregister.
- Both sides of that diff must be in the same portable `${TOKEN}` space. The live
  file holds localized absolute paths, so the caller portabilizes before planning;
  comparing raw reads every hook as changed.

## 5. Identity, idempotency & safety

**Marker.** Every hook config-sync registers gets a trailing marker appended to its
command string: `… # config-sync:<hook_id>` (e.g. `# config-sync:ab12cd34ef56`).
The `hook_id` is a short hash of the clean (pre-marker) declaration, so appending
the marker never feeds back into the identity. This is:

- schema-safe (no extra JSON keys the settings schema might reject),
- shell-safe (a trailing `#` comment is ignored by the shell that runs the hook),
- and invisible to #67's path rewriter (it only rewrites path prefixes).

**Idempotency.** `plan_hook_wiring` treats a declared hook as already-present iff
`settings.json` contains a hook whose command carries `# config-sync:<hook_id>`
*and* whose command still equals the declaration. Present and matching → skipped;
present but changed (or found via `registrations_by_script`) → `update` in place;
absent → `register`. Re-running after an apply yields an empty plan.

Comparison happens in the **live file's** space: the declaration is localized
before it is compared or written. Planning in portable space instead is unsound —
`portabilize` is not the inverse of `localize` (an absolute path outside every
declared root becomes a `${HOME}` token no declaration contains; with nested
roots the longest prefix wins), so affected hooks read as changed on every run.

**Never clobber hand-added hooks.** config-sync only ever recognises marked hooks
as "its own." A hook a human added by hand (no marker) is never matched, moved,
or removed by the wiring — even if it points at the same script.

> **Amended (2026-08-02):** the wiring now *updates* its own marked hooks as
> well as adding them (§11.1), so "only ever adds" no longer holds for them. The
> hand-added guarantee is unchanged with one named exception: `hooks-prune
> --include-unmanaged`, which exists precisely to reach them and is fenced
> behind its own separate confirmation.

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

- Does **not** touch hand-added or supacode-managed hooks. *(Still true for the
  wiring. `hooks-prune --include-unmanaged` can reach them, but only when the
  operator asks for it by name — see §11.1.)*
- Does **not** repackage `mente-apex-memory` as a plugin (future option).
- Does **not** invent hooks or change what any hook does.
- Does **not** survive an `event` or `matcher` edit: both are still inside the
  identity hash, so changing either orphans the previous registration. Open —
  see §11.1, "Scope of the resolution".
- Does **not** delete on any evidence that depends on this process's
  environment. A program absent from *this* PATH, a relative path it cannot
  resolve without the hook's cwd, and any command containing `$` are all
  reported and left alone.
- Does **not** wire a declaration whose script is absent from this machine. It
  would be registered by apply, deleted by prune as a dead target, and
  registered again by the next apply. Skipped with a reason instead; the next
  apply after the repo is properly checked out wires it.

> **Superseded (2026-08-02):** *"Does not unregister or prune hooks (union-only,
> like snapshot import)."* Union-only turned out to be the defect, not the
> safeguard — see §11.1.

## 11. Resolved questions

### 11.1 — Update-in-place, and the pruning that came with it

> *Original: should `hooks-apply` also update a marked hook whose declaration
> changed (e.g. matcher edited), or only add missing ones? Leaning:
> update-in-place for marked hooks (safe, since we own them), but MVP could
> add-only. Decide in plan.*

**Resolved 2026-08-02 — update-in-place, as the original leaning suggested.**
The MVP shipped add-only, and that is precisely what broke.

Identity was `sha1(root_token, event, matcher, full_command)`, so *any* edit to
a declaration minted a new `hook_id`. The previous registration was never
matched again and could never be reached, let alone updated. Add-only was not a
smaller version of update-in-place; it was a structural leak. Observed on a real
machine: `protect_brain.py` wired four times and `enforce_gates.py` three times,
from three install locations. Once one of those locations went away, the dead
hook printed an error on every tool call in every project.

What shipped:

- Identity keys on the **script** (`script_key_of`), not the whole command, so
  changing the interpreter in front of it resolves to the same registration. A
  repo can pin identity outright with an `"id"` in its `hooks.json`.
- `plan_hook_wiring` emits an `update` verb carrying the `location` of the
  existing entry; `execute_hook_plan` rewrites in place rather than appending.
- A marker written under the old scheme is re-found by
  `registrations_by_script()` — `(event, matcher, script filename)`, read off the
  **registered** command. A key claimed by two registrations is dropped rather
  than guessed at.

  The first attempt at this carried the old full-command hash on the declaration
  (`legacy_hook_id`) and did not survive review: that hash is taken over the
  *currently declared* command, while the marker in the wild was taken over the
  command *as registered*. The two agree only when the command has not changed —
  i.e. only for the hook that did not need migrating. A plugin update that ships
  the new scheme and a relocated command together matched nothing and appended a
  permanent duplicate, which `hooks-prune` would not remove because a same-named
  script from elsewhere is only advisory.
- Planning happens in portable `${TOKEN}` space. Declarations are tokenised and
  the live file is localized; comparing them raw reads every hook as changed and
  rewrites it on every run.

Update-in-place fixes hooks config-sync still declares. It cannot help one whose
declaration is simply gone, so the same change added the repair side:
`hooks-doctor` (read-only, reports every hook in the file) and `hooks-prune`
(definitive findings only — missing target, exact duplicate — and only
config-sync's own entries unless `--include-unmanaged`). Advisory findings are
reported, never auto-repaired. This is what supersedes the union-only line
in §10.

**Scope of the resolution.** The question's own example — *"e.g. matcher
edited"* — is **not** covered. `event` and `matcher` remain inside the identity
hash, so editing either still mints a new id and leaves the previous
registration orphaned; only *command* edits update in place. That residual
orphan class is real and belongs in §10 until closed. A repo that needs to
survive an event or matcher change can pin identity with an explicit `"id"`,
which is hashed in their place.

**Ambiguity is refused, not guessed.** Two declarations for one event and matcher
that resolve to the same script derive the same `hook_id`. Wiring both meant they
took turns overwriting each other's registration on every run, leaving one
permanently unwired. Both are now skipped with a message naming the fix (give
each an explicit `"id"`).

### 11.2 — Surfacing wire-hooks in `/config-sync`

> *Original: surface wire-hooks automatically in `/config-sync`, or keep it an
> explicit opt-in command for the first release? Leaning: show the plan
> automatically but never apply without consent.*

**Resolved as leaning.** `/config-sync` Step 4c runs `hooks-plan` automatically
and shows the actions; `hooks-apply` runs only after a single explicit consent
gate. Step 4d does the same for `hooks-doctor` / `hooks-prune`, with
`--include-unmanaged` behind a second, separate confirmation.
