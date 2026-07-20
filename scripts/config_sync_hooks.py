"""Hook provisioning for config-sync — the wire-hooks channel (#68).

Discovers `hooks/hooks.json` declarations under the named roots from
config_sync_roots (#67), diffs them against the live settings.json, and
registers any missing hooks in portable ${TOKEN} form behind a consent gate.

DIP: the planner is pure (data in, plan out); the executor depends only on the
SettingsHost Protocol. Union-only — config-sync only ever adds hooks it marks as
its own, and never touches hand-added or unmarked hooks.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
MARKER_PREFIX = "# config-sync:"
_MARKER_RE = re.compile(re.escape(MARKER_PREFIX) + r"([0-9a-f]{12})")


def resolve_command(command: str, root_token: str) -> str:
    """Map the native ${CLAUDE_PLUGIN_ROOT} placeholder onto the discovering
    root's portable token, so the stored registration is machine-independent."""
    return command.replace(PLUGIN_ROOT_PLACEHOLDER, "${" + root_token + "}")


def hook_id_of(root_token: str, event: str, matcher: str, command: str) -> str:
    """Stable 12-hex identity for a declared hook, over its clean (pre-marker)
    fields. Null-joined so no field boundary can be forged by another."""
    payload = "\0".join([root_token, event, matcher, command]).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def marker_for(hook_id: str) -> str:
    return MARKER_PREFIX + hook_id


def registered_hook_ids(settings: dict) -> set:
    """Every config-sync hook_id already present in settings.json, read from the
    marker trailing each managed hook's command."""
    found = set()
    for matcher_groups in settings.get("hooks", {}).values():
        for matcher_group in matcher_groups:
            for hook in matcher_group.get("hooks", []):
                command = hook.get("command", "")
                if isinstance(command, str):
                    match = _MARKER_RE.search(command)
                    if match:
                        found.add(match.group(1))
    return found


@dataclass(frozen=True)
class DeclaredHook:
    hook_id: str
    event: str
    matcher: str
    command: str            # tokenised (${TOKEN}/...), pre-marker
    timeout: Optional[int]


@dataclass
class HookAction:
    verb: str                       # always "register" (union-only)
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


def discover_declarations(registry) -> List[DeclaredHook]:
    """Read each named root's hooks/hooks.json and flatten it into DeclaredHooks
    with resolved tokens and stable ids. Missing/malformed files are skipped."""
    declarations: List[DeclaredHook] = []
    for root in registry.named_roots():
        declaration_path = Path(root.path) / "hooks" / "hooks.json"
        try:
            data = json.loads(declaration_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for event, matcher_groups in data.get("hooks", {}).items():
            if not isinstance(matcher_groups, list):
                continue
            for matcher_group in matcher_groups:
                matcher = matcher_group.get("matcher", "")
                for hook in matcher_group.get("hooks", []):
                    raw_command = hook.get("command")
                    if not isinstance(raw_command, str):
                        continue
                    command = resolve_command(raw_command, root.token)
                    declarations.append(DeclaredHook(
                        hook_id=hook_id_of(root.token, event, matcher, command),
                        event=event,
                        matcher=matcher,
                        command=command,
                        timeout=hook.get("timeout"),
                    ))
    return declarations


def plan_hook_wiring(declarations: List[DeclaredHook], settings: dict) -> HookPlan:
    """Pure planner: emit a register action for every declared hook whose id is
    not already marked in settings. Never unregisters; unmarked hooks are ignored."""
    already_registered = registered_hook_ids(settings)
    plan = HookPlan()
    for declaration in declarations:
        if declaration.hook_id in already_registered:
            plan.skipped.append(f"{declaration.hook_id}: already registered")
            continue
        plan.actions.append(HookAction("register", declaration.hook_id, {
            "event": declaration.event,
            "matcher": declaration.matcher,
            "command": declaration.command,
            "timeout": declaration.timeout,
        }))
    return plan


def execute_hook_plan(plan: HookPlan, host: SettingsHost) -> HookResult:
    """Apply each register action as a new marker-tagged matcher group. One write
    total, only when there is at least one action (idempotent no-op otherwise)."""
    result = HookResult(skipped=list(plan.skipped))
    if not plan.actions:
        return result
    settings = host.read_settings()
    hooks_block = settings.setdefault("hooks", {})
    for action in plan.actions:
        event_groups = hooks_block.setdefault(action.detail["event"], [])
        marked_command = action.detail["command"] + " " + marker_for(action.hook_id)
        hook_entry = {"type": "command", "command": marked_command}
        if action.detail.get("timeout") is not None:
            hook_entry["timeout"] = action.detail["timeout"]
        event_groups.append({"matcher": action.detail["matcher"], "hooks": [hook_entry]})
        result.outcomes.append(HookOutcome(action.hook_id, ok=True))
    host.write_settings(settings)
    return result
