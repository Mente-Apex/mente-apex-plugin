"""Hook provisioning for config-sync — the wire-hooks channel (#68).

Discovers `hooks/hooks.json` declarations under the named roots from
config_sync_roots (#67), diffs them against the live settings.json, and
registers any missing hooks in portable ${TOKEN} form behind a consent gate.

DIP: the planner is pure (data in, plan out); the executor depends only on the
SettingsHost Protocol.

Scope of what this module will edit: hooks it marks as its own, and nothing
else. A hand-added or unmarked hook is never touched. Within its own, it both
registers what is missing and updates in place what has moved — appending only
was the original design, and it leaked: identity was hashed over the whole
command, so any change minted a new id and stranded the previous registration
forever. Removal is not here at all; that is config_sync_hook_doctor's job,
behind its own gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
MARKER_PREFIX = "# config-sync:"
_MARKER_RE = re.compile(re.escape(MARKER_PREFIX) + r"([0-9a-f]{12})")

# A ${TOKEN}-rooted path inside a declared command, captured from the separator
# on so the key is the path relative to its root.
_TOKEN_PATH_RE = re.compile(r"\$\{[A-Za-z0-9_]+\}(/[^\s\"']*)")

# Suffixes that mark an argument as data the hook reads rather than the program
# it runs, so `inject-context.sh directive.txt` keys on the script.
DATA_SUFFIXES = frozenset(
    {".txt", ".json", ".md", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}
)


def resolve_command(command: str, root_token: str) -> str:
    """Map the native ${CLAUDE_PLUGIN_ROOT} placeholder onto the discovering
    root's portable token, so the stored registration is machine-independent."""
    return command.replace(PLUGIN_ROOT_PLACEHOLDER, "${" + root_token + "}")


def hook_id_of(root_token: str, event: str, matcher: str, command: str) -> str:
    """Stable 12-hex identity for a declared hook, over its clean (pre-marker)
    fields. Null-joined so no field boundary can be forged by another."""
    payload = "\0".join([root_token, event, matcher, command]).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def script_key_of(command: str) -> str:
    """The relocation-stable part of a tokenised command: the script it runs.

    Keying identity on the whole command string was the defect this fixes —
    changing the interpreter (`python3 X` becoming `${ROOT}/bin/py X`) minted a
    fresh id, so the previous registration was never matched again and survived
    forever as a second, eventually-broken copy. The script is the last
    ${TOKEN}-rooted path that is not obviously a data argument; a command with
    no rooted path has nothing more stable to key on than itself.
    """
    return choose_script_path(_TOKEN_PATH_RE.findall(strip_marker(command))) or command


def choose_script_path(paths: list[str]) -> str | None:
    """Which of `paths` is the program a command runs, rather than an argument.

    The last one wins: an interpreter always precedes the script it runs, so
    taking the last is what makes `python3 X` and `${ROOT}/bin/py X` agree.
    Data suffixes are excluded first, so `inject-context.sh directive.txt`
    still names the shell script. Returns None when there is nothing to choose.
    """
    if not paths:
        return None
    scripts = [path for path in paths if Path(path).suffix.lower() not in DATA_SUFFIXES]
    return (scripts or paths)[-1]


def script_name_of(command: str) -> str | None:
    """The bare filename of the script `command` runs, in either space.

    `script_key_of` only sees `${TOKEN}`-rooted paths, so it cannot read a
    command that has already been localized to absolute paths — and the live
    settings.json is always localized. This reads both, which is what lets a
    registration be re-found after its command was rewritten. Scoped by event and
    matcher at the call site, and abandoned when ambiguous.
    """
    try:
        tokens = shlex.split(strip_marker(command))
    except ValueError:
        return None
    paths = [
        token
        for token in tokens
        if token.startswith("/") or token.startswith("~/") or "${" in token
    ]
    chosen = choose_script_path(paths)
    return os.path.basename(chosen) if chosen else None


def marker_for(hook_id: str) -> str:
    return MARKER_PREFIX + hook_id


def mark_command(command: str, hook_id: str) -> str:
    """`command` as config-sync will WRITE it: the invocation plus its marker.

    The single writer of that composition. `plan_hook_wiring` must build its
    proposed pseudo-site with exactly the bytes `execute_hook_plan` will store,
    or a tier-1 (marker) rejection matches the live registration and misses the
    declaration that would re-create it — a silently inert rejection.
    """
    return command + " " + marker_for(hook_id)


def hook_id_in(command: str) -> str | None:
    """The config-sync hook_id marked on `command`, or None when the command is
    not one of ours. The single reader of the marker format."""
    match = _MARKER_RE.search(command)
    return match.group(1) if match else None


def strip_marker(command: str) -> str:
    """`command` with any config-sync marker removed — the form to compare,
    parse, or re-mark, since the marker is bookkeeping rather than invocation."""
    return _MARKER_RE.sub("", command).rstrip()


def registered_hook_ids(settings: dict) -> set:
    """Every config-sync hook_id already present in settings.json, read from the
    marker trailing each managed hook's command."""
    found = set()
    for matcher_groups in settings.get("hooks", {}).values():
        for matcher_group in matcher_groups:
            for hook in matcher_group.get("hooks", []):
                command = hook.get("command", "")
                if isinstance(command, str):
                    hook_id = hook_id_in(command)
                    if hook_id:
                        found.add(hook_id)
    return found


@dataclass(frozen=True)
class DeclaredHook:
    hook_id: str
    event: str
    matcher: str
    command: str  # tokenised (${TOKEN}/...), pre-marker
    timeout: int | None


def declared_hook(
    root_token: str,
    event: str,
    matcher: str,
    command: str,
    timeout: int | None = None,
    explicit_id: str | None = None,
) -> DeclaredHook:
    """Build a DeclaredHook, composing its identity in the one place that knows
    how. `explicit_id` is the declaring repo's own name for the hook (an `id` in
    hooks.json) and outranks the derived script key, so a repo that renames its
    script keeps the registration."""
    identity_key = explicit_id or script_key_of(command)
    return DeclaredHook(
        hook_id=hook_id_of(root_token, event, matcher, identity_key),
        event=event,
        matcher=matcher,
        command=command,
        timeout=timeout,
    )


@dataclass(frozen=True)
class HookSite:
    """Where one hook entry lives in the settings hooks block, and what it runs.

    Shared vocabulary: the wiring locates its own registrations with it and the
    doctor locates every entry with it, so the block's shape is decoded once.
    """

    event: str
    group_index: int
    hook_index: int
    matcher: str
    command: str


def hook_sites(settings: dict) -> list[HookSite]:
    """Every hook entry in `settings`, in document order. Malformed entries are
    skipped one by one rather than aborting the walk — a reader that dies on the
    first odd entry cannot report on the file that most needs reporting on."""
    sites: list[HookSite] = []
    for event, matcher_groups in settings.get("hooks", {}).items():
        if not isinstance(matcher_groups, list):
            continue
        for group_index, matcher_group in enumerate(matcher_groups):
            if not isinstance(matcher_group, dict):
                continue
            matcher = matcher_group.get("matcher") or ""
            hooks = matcher_group.get("hooks", [])
            if not isinstance(hooks, list):
                continue
            for hook_index, hook in enumerate(hooks):
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command")
                if not isinstance(command, str):
                    continue
                sites.append(HookSite(event, group_index, hook_index, matcher, command))
    return sites


@dataclass(frozen=True)
class RegisteredHook:
    """A config-sync-marked entry found in settings.json: its identity, where it
    sits, and the command with the marker taken back off."""

    hook_id: str
    site: HookSite
    command: str


def registered_hooks(settings: dict) -> dict:
    """Every config-sync registration in `settings`, keyed by hook_id. First
    occurrence wins, so a stray second copy never hides the original."""
    found: dict = {}
    for site in hook_sites(settings):
        hook_id = hook_id_in(site.command)
        if hook_id and hook_id not in found:
            found[hook_id] = RegisteredHook(hook_id, site, strip_marker(site.command))
    return found


def registrations_by_script(settings: dict) -> dict:
    """config-sync registrations reachable by (event, matcher, script name).

    This is how a registration marked under an older identity scheme is found
    again. Hashing the previous id over the *declared* command could only ever
    match a hook whose command had not changed — precisely the hook that did not
    need migrating. Meanwhile the hook that had moved was re-registered as a
    second, permanent copy that prune would not touch, because a same-named
    script from elsewhere is only an advisory finding.

    A key claimed by two registrations is dropped rather than guessed at: better
    to leave both alone and register nothing than to rewrite the wrong one.
    """
    found: dict = {}
    ambiguous = set()
    for registration in registered_hooks(settings).values():
        script_name = script_name_of(registration.command)
        if script_name is None:
            continue
        key = (registration.site.event, registration.site.matcher, script_name)
        if key in found:
            ambiguous.add(key)
            continue
        found[key] = registration
    for key in ambiguous:
        del found[key]
    return found


@dataclass
class HookAction:
    verb: str  # "register" (new) or "update" (rewrite an existing registration)
    hook_id: str
    detail: dict = field(default_factory=dict)


@dataclass
class HookPlan:
    actions: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


@runtime_checkable
class SettingsHost(Protocol):
    def read_settings(self) -> dict: ...

    def write_settings(self, settings: dict) -> None: ...


@dataclass
class HookOutcome:
    hook_id: str
    ok: bool
    message: str = ""


@dataclass
class HookResult:
    outcomes: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def discover_declarations(registry) -> list[DeclaredHook]:
    """Read each named root's hooks/hooks.json and flatten it into DeclaredHooks
    with resolved tokens and stable ids. Missing/malformed files are skipped."""
    declarations: list[DeclaredHook] = []
    for root in registry.named_roots():
        declaration_path = Path(root.path) / "hooks" / "hooks.json"
        try:
            data = json.loads(declaration_path.read_text(encoding="utf-8"))
        except FileNotFoundError, json.JSONDecodeError, OSError:
            continue
        if not isinstance(data, dict):
            continue
        for event, matcher_groups in data.get("hooks", {}).items():
            if not isinstance(matcher_groups, list):
                continue
            for matcher_group in matcher_groups:
                if not isinstance(matcher_group, dict):
                    continue
                matcher = matcher_group.get("matcher", "")
                hooks = matcher_group.get("hooks", [])
                if not isinstance(hooks, list):
                    continue
                for hook in hooks:
                    if not isinstance(hook, dict):
                        continue
                    raw_command = hook.get("command")
                    if not isinstance(raw_command, str):
                        continue
                    command = resolve_command(raw_command, root.token)
                    explicit_id = hook.get("id")
                    declarations.append(
                        declared_hook(
                            root.token,
                            event,
                            matcher,
                            command,
                            timeout=hook.get("timeout"),
                            explicit_id=(
                                explicit_id if isinstance(explicit_id, str) else None
                            ),
                        )
                    )
    return declarations


def identity(command: str) -> str:
    """The default command transform: none. Substituted at the CLI edge."""
    return command


@runtime_checkable
class CommandChecker(Protocol):
    """Whether a command could actually run on this machine.

    One method, because the planner has exactly one question. Widening this to
    the doctor's `TargetProbe` would hand the planner `resolve` and `locate` it
    has no use for, and would drag knowledge of filesystems into a pure module.
    """

    def is_runnable(self, command: str) -> bool: ...


class AssumeRunnable:
    """The default CommandChecker: makes no claim, blocks nothing.

    A null object rather than an `if checker is not None` branch, so the planner
    has one path and no caller is obliged to care about the filesystem.
    """

    def is_runnable(self, command: str) -> bool:
        return True


def plan_hook_wiring(
    declarations: list[DeclaredHook],
    settings: dict,
    localize=identity,
    checker: CommandChecker | None = None,
    policy=None,
) -> HookPlan:
    """Pure planner: register a declared hook that is not yet marked, and update
    one that is marked but no longer matches what the repo declares.

    Update is what makes a relocation survivable. Without it the wiring could
    only append, so every rewired hook left its predecessor behind to rot.
    Unmarked hooks stay untouched — config-sync still only ever edits its own.

    `settings` is the live file, holding machine-absolute commands. `localize`
    maps a declaration's portable `${TOKEN}` command into that same space, and is
    injected because this module must not know how a machine resolves roots.
    Planning in portable space instead is not an option: `portabilize` is not the
    inverse of `localize` — an absolute path outside any declared root becomes a
    `${HOME}` token that no declaration contains, and with nested roots the
    longest prefix wins — so a hook would read as changed on every run and be
    rewritten forever.

    `checker` decides whether a declared command could run here. A repo that
    declares a hook whose script is absent would otherwise be wired by apply,
    deleted by prune as a dead target, and wired again by the next apply — a flap
    with no stable state. Declining to wire it breaks the cycle. Injected and
    defaulted to a null object, so the planner itself stays pure.

    `policy` is the rejection ledger, injected and defaulted to a null object so
    every existing caller is unaffected. A rejected declaration is never
    registered — that is what stops it being proposed on every sync. It is NOT
    unregistered if already present: config-sync only edits its own marked
    entries, and removing a registration is `hooks-prune`'s job. The two compose.
    """
    # Deferred imports: siblings, not a package.
    import config_sync_rejection_hooks as rejection_hooks_module
    import config_sync_rejections as rejections_module

    policy = policy if policy is not None else rejections_module.NullRejectionPolicy()

    plan = HookPlan()

    addressor = rejection_hooks_module.HookRegistrationAddressor()
    # Bound once: `policy.all()` re-reads every ledger file, and asking per
    # declaration turned one plan into O(N) full ledger reads.
    hook_rejections = _active_hook_rejections(policy)
    kept_declarations = []
    for declaration in declarations:
        # A declaration has no position in the block, so its sentinel indices say
        # "proposed, not present". Localized because this planner works in
        # localized space -- see the note on `localize` above, and MARKED because
        # that is exactly what `execute_hook_plan` will write: a tier-1 (marker)
        # rejection is recorded against the marked live command, so a pre-marker
        # candidate would never match it and the rejection would be inert.
        proposed = HookSite(
            event=declaration.event,
            group_index=-1,
            hook_index=-1,
            matcher=declaration.matcher,
            command=mark_command(localize(declaration.command), declaration.hook_id),
        )
        rejected_record = _matching_hook_rejection(
            policy, addressor, proposed, hook_rejections
        )
        if rejected_record is not None:
            plan.skipped.append(
                f"{declaration.hook_id}: rejected in the config-sync ledger "
                f"({rejected_record.address})"
            )
            continue
        kept_declarations.append(declaration)
    declarations = kept_declarations

    checker = checker or AssumeRunnable()

    # Two declarations that derive the same identity would take turns
    # overwriting one another's registration, run after run, leaving one of them
    # permanently unwired. Refuse both, and say what would fix it.
    collisions = {
        hook_id
        for hook_id, count in Counter(
            declaration.hook_id for declaration in declarations
        ).items()
        if count > 1
    }

    registered = registered_hooks(settings)
    by_script = registrations_by_script(settings)

    # The `by_script` fallback keys on (event, matcher, script basename) and
    # deliberately omits the root token that `hook_id` includes. Two named
    # roots shipping a same-named script under the same event and matcher
    # therefore have DIFFERENT hook_ids -- so the collision guard above cannot
    # see them -- but the SAME fallback key. Each run, each declaration found
    # the other's registration through the fallback and "updated" it out of
    # existence, reported ok=True, and listed the displaced hook as already
    # registered. It never converged; one of the two was always unwired.
    #
    # The fallback is what is ambiguous here, not the declarations. Both are
    # perfectly well identified by their own hook_id, so the fix is to stop
    # using the fallback for them rather than to refuse them: each registers
    # under its own identity and neither displaces the other.
    ambiguous_fallback = {
        key
        for key, count in Counter(
            _fallback_key(declaration) for declaration in declarations
        ).items()
        if count > 1 and key is not None
    }

    for declaration in declarations:
        if declaration.hook_id in collisions:
            plan.skipped.append(
                f"{declaration.command}: ambiguous — another declared hook for the "
                f"same event and matcher resolves to the same script. Give each an "
                f'explicit "id" in hooks.json to tell them apart.'
            )
            continue

        wire_command = localize(declaration.command)
        if not checker.is_runnable(wire_command):
            plan.skipped.append(
                f"{wire_command}: the declared script is not on this machine — "
                f"not wired (it would only be pruned again as a dead target)"
            )
            continue

        existing = registered.get(declaration.hook_id)
        if existing is None:
            fallback_key = _fallback_key(declaration)
            if fallback_key in ambiguous_fallback:
                # Not silent. Refusing to guess which of two same-named
                # scripts owns a registration marked under an older identity
                # is right, but it leaves that registration orphaned: still
                # marked, still firing, and no longer claimed by any
                # declaration. `hooks-doctor` reclaims it as an exact
                # duplicate of the one being registered now, so the operator
                # needs to know to run it.
                if by_script.get(fallback_key) is not None:
                    plan.skipped.append(
                        f"{declaration.command}: another declared hook ships a "
                        f"same-named script under the same event and matcher, "
                        f"so an existing registration cannot be attributed to "
                        f"either. Registering this one under its own id; run "
                        f"`hooks-doctor` to clear the now-orphaned entry, or "
                        f'give each declaration an explicit "id" in hooks.json.'
                    )
            else:
                existing = by_script.get(fallback_key)

        if existing is None:
            plan.actions.append(
                HookAction(
                    "register", declaration.hook_id, _detail(declaration, wire_command)
                )
            )
            continue
        if (
            existing.hook_id == declaration.hook_id
            and existing.command == wire_command
            and _timeout_of(settings, existing.site) == declaration.timeout
        ):
            plan.skipped.append(f"{declaration.hook_id}: already registered")
            continue
        plan.actions.append(
            HookAction(
                "update",
                declaration.hook_id,
                _detail(declaration, wire_command, match_hook_id=existing.hook_id),
            )
        )
    return plan


def _active_hook_rejections(policy) -> list:
    """The `(record, tier)` pairs worth testing a candidate site against.

    Hoisted out of the per-declaration loop: `policy.all()` re-reads every ledger
    file, so asking it once per declaration made a plan cost O(N) full reads —
    the same amplification `CompositeRejectionPolicy.is_rejected` already binds
    against. Records whose tier does not parse are dropped here rather than in
    the loop; they were skipped before too.
    """
    pairs = []
    for record in policy.all():
        if record.kind != "hook-registration" or record.revives is not None:
            continue
        # fmt: off
        # PEP 758 lets black strip these parens (Python 3.14). Kept parenthesized
        # for explicitness -- black would otherwise write the bare tuple form.
        try:
            tier = int(record.tier)
        except (TypeError, ValueError):
            continue
        # fmt: on
        pairs.append((record, tier))
    return pairs


def _matching_hook_rejection(policy, addressor, site, active=None):
    """The first active hook-registration rejection whose address matches `site`
    at its own recorded tier, or None.

    Walks records rather than calling `policy.is_rejected`, because a hook
    address alone is not enough to ask that question -- the tier that produced it
    is part of the identity, and only the record knows it.

    `active` is the pre-bound result of `_active_hook_rejections`, so a caller
    with many sites pays for the ledger read once. Fetched here when omitted, so
    a single-site caller stays a one-liner.
    """
    import config_sync_rejections as rejections_module

    for record, tier in _active_hook_rejections(policy) if active is None else active:
        if not addressor.matches(record.address, tier, site):
            continue
        target = rejections_module.RejectionTarget(
            kind=record.kind, address=record.address
        )
        if policy.is_rejected(target, ""):
            return record
    return None


def _timeout_of(settings: dict, site: HookSite):
    """The timeout currently stored at `site`, so a declaration that changes only
    its timeout is not reported as already-registered."""
    entry = _entry_at(settings, site)
    return entry.get("timeout") if entry else None


def _detail(
    declaration: DeclaredHook, wire_command: str, match_hook_id: str | None = None
) -> dict:
    detail = {
        "event": declaration.event,
        "matcher": declaration.matcher,
        "command": wire_command,
        "timeout": declaration.timeout,
    }
    if match_hook_id is not None:
        detail["match_hook_id"] = match_hook_id
    return detail


def _entry_at(settings: dict, site: HookSite) -> dict | None:
    """The hook entry dict at `site`, or None if the shape no longer holds."""
    groups = settings.get("hooks", {}).get(site.event)
    if not isinstance(groups, list) or site.group_index >= len(groups):
        return None
    group = groups[site.group_index]
    if not isinstance(group, dict):
        return None
    hooks = group.get("hooks")
    if not isinstance(hooks, list) or site.hook_index >= len(hooks):
        return None
    entry = hooks[site.hook_index]
    return entry if isinstance(entry, dict) else None


def execute_hook_plan(plan: HookPlan, host: SettingsHost) -> HookResult:
    """Apply the plan: append a new marker-tagged matcher group per register,
    rewrite the marked entry in place per update. One write total, only when
    something actually changed (idempotent no-op otherwise).

    An update re-finds its entry by marker in the settings *this* function read,
    rather than trusting an index the planner captured from an earlier read. The
    positional form would silently overwrite a bystander if anything edited the
    file in between; the marker is the identity, so use it.
    """
    result = HookResult(skipped=list(plan.skipped))
    if not plan.actions:
        return result
    settings = host.read_settings()
    hooks_block = settings.setdefault("hooks", {})
    registered = registered_hooks(settings)
    wrote_anything = False

    for action in plan.actions:
        marked = mark_command(action.detail["command"], action.hook_id)
        match_hook_id = action.detail.get("match_hook_id")

        if match_hook_id is None:
            entry = {"type": "command"}
            _apply_declared_fields(entry, action, marked)
            hooks_block.setdefault(action.detail["event"], []).append(
                {"matcher": action.detail["matcher"], "hooks": [entry]}
            )
            wrote_anything = True
            result.outcomes.append(HookOutcome(action.hook_id, ok=True))
            continue

        existing = registered.get(match_hook_id)
        entry = _entry_at(settings, existing.site) if existing else None
        if entry is None:
            result.outcomes.append(
                HookOutcome(
                    action.hook_id,
                    ok=False,
                    message="settings.json changed since it was planned; nothing "
                    "rewritten for this hook — re-run hooks-plan",
                )
            )
            continue
        _apply_declared_fields(entry, action, marked)
        wrote_anything = True
        result.outcomes.append(HookOutcome(action.hook_id, ok=True))

    if wrote_anything:
        host.write_settings(settings)
    return result


def _fallback_key(declaration):
    """The key `registrations_by_script` is looked up by, for one declaration.

    Extracted so the planner's ambiguity check and its lookup cannot drift into
    computing the key two different ways.
    """
    script_name = script_name_of(declaration.command)
    if script_name is None:
        return None
    return (declaration.event, declaration.matcher, script_name)


def _apply_declared_fields(
    entry: dict, action: HookAction, marked_command: str
) -> None:
    """Bring `entry` in line with what the declaration says, in place.

    Everything a declaration does not own — `statusMessage` most notably, which
    this plugin's own hooks.json declares — belongs to whoever put it there and
    survives the rewrite.

    A declaration that no longer sets `timeout` REMOVES it, rather than leaving
    the old value behind. Setting-only meant a hooks.json that dropped
    `"timeout": 10` could never reach its declared state: the planner compared
    the entry's surviving timeout against the declaration's `None`, found them
    different, emitted an `update`, rewrote settings.json and reported success
    -- on every single run, forever.
    """
    entry["command"] = marked_command
    timeout = action.detail.get("timeout")
    if timeout is None:
        entry.pop("timeout", None)
    else:
        entry["timeout"] = timeout


class CorruptSettingsError(RuntimeError):
    """settings.json exists but does not parse.

    Distinct from "there is no settings.json yet", which is an ordinary state
    with an obvious answer (`{}`). This one has no safe answer: the file holds
    configuration nothing can read, and every write path would replace it.
    """


class ClaudeSettingsHost:
    """Real SettingsHost over ~/.claude/settings.json. Injected into the CLI
    wrappers; faked in tests.

    Writes atomically: this file is the user's global configuration, and a
    truncated one breaks every session on the machine. Rendering to a temporary
    file in the same directory and renaming makes the swap all-or-nothing.
    """

    def __init__(self, claude_dir: Path):
        self._settings_path = claude_dir / "settings.json"

    def read_settings(self) -> dict:
        """The parsed settings, or `{}` when the file does not exist yet.

        A file that exists but does not parse is NOT `{}`. Folding
        `JSONDecodeError` into the empty dict meant one trailing comma turned
        `hooks-apply` into "the settings are empty, write my hooks into them" --
        rewriting the file as `{"hooks": {...}}` and destroying `permissions`,
        `model`, `env` and `statusLine`. `BackingUpSettingsHost` snapshots what
        this method returns, so the rollback file was `{}` too and the original
        was gone for good.

        Raising instead stops the command before any write, which is the only
        safe reading of "I cannot tell what is in this file".
        """
        try:
            raw = self._settings_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CorruptSettingsError(
                f"{self._settings_path} exists but is not valid JSON "
                f"({exc}); refusing to touch it, because rewriting it would "
                "discard whatever it currently holds. Fix the syntax (or move "
                "the file aside) and run this again"
            ) from exc

    def write_settings(self, settings: dict) -> None:
        rendered = json.dumps(settings, indent=2, ensure_ascii=False)
        scratch = self._settings_path.with_suffix(".json.config-sync-tmp")
        scratch.write_text(rendered, encoding="utf-8")
        os.replace(scratch, self._settings_path)


class BackingUpSettingsHost:
    """A SettingsHost that snapshots the file before the first write.

    A decorator rather than a branch inside the real host: only the destructive
    commands need a rollback path, and the ones that do should say so at the
    composition root instead of every host acquiring the behaviour.
    """

    def __init__(self, inner: SettingsHost, backup_path: Path):
        self._inner = inner
        self._backup_path = backup_path
        self._saved = False

    def read_settings(self) -> dict:
        return self._inner.read_settings()

    def write_settings(self, settings: dict) -> None:
        if not self._saved:
            self._backup_path.write_text(
                json.dumps(self._inner.read_settings(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._saved = True
        self._inner.write_settings(settings)

    @property
    def backup_path(self) -> Path:
        return self._backup_path
