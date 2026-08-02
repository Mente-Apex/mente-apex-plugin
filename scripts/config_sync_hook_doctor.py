"""Diagnosis and pruning of the live hooks block — the read/repair side of
config-sync's wire-hooks channel.

Wiring (config_sync_hooks) only ever registers or updates the hooks it declares.
It has no answer for the entry that goes bad — a hook whose script moved, or a
second copy of the same guard wired from a different install location. Those
persist, and once a target disappears every tool call in every project prints a
hook error.

This module is the missing half, and it deletes from a file the operator did not
ask us to edit. So the governing rule is: **only an unambiguous, locally
verifiable fact may justify a deletion.** A finding is `DEFINITIVE` only when the
command names an absolute path that is not on disk, or when two entries are the
same invocation down to their arguments. Everything else — a program not on
*this* process's PATH, a relative path we cannot resolve without the hook's cwd,
a same-named script from another install — is advisory: reported to the operator,
never acted on.

DIP: every filesystem question goes through the `TargetProbe` Protocol, so the
diagnostic engine is pure — tests state what exists rather than inheriting
whatever the machine happens to have. The planner is pure (data in, plan out) and
the executor depends only on `SettingsHost`, matching the plan/execute split the
rest of config-sync uses.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import config_sync_hooks

# Definitive — the hook cannot be doing what it was registered to do, and the
# evidence does not depend on this process's environment.
MISSING_TARGET = "missing-target"
DUPLICATE_COMMAND = "duplicate-command"

# Advisory — reported, never auto-repaired.
MISSING_ON_PATH = "missing-on-path"
UNRESOLVABLE = "unresolvable"
DUPLICATE_SCRIPT = "duplicate-script"
OPAQUE = "opaque"

DEFINITIVE_FINDINGS = frozenset({MISSING_TARGET, DUPLICATE_COMMAND})

# A command carrying any of these is a shell fragment or depends on the runtime
# environment, so no static claim about it can justify a deletion.
#
# `$` is here for a reason that cost a working hook in review: `$CLAUDE_PROJECT_DIR/
# .claude/hooks/check.sh` is the idiom Claude Code's own hook docs recommend, and
# config-sync itself writes `${CONFIG_SYNC_ROOT_X}/...` whenever a token arrives
# from a machine whose root is not declared here. Neither expands during probing,
# so both read as missing and were pruned — including config-sync's own marked
# entries, on the default path.
SHELL_METACHARACTERS = (";", "&&", "||", "|", "$", "`", ">", "<", "\n", "&")

GLOB_CHARACTERS = ("*", "?", "[")

# Programs that take a script path as their first non-flag argument. Used only to
# decide what else is worth probing; an unrecognised program simply means we
# probe less, never more.
INTERPRETERS = frozenset(
    {"sh", "bash", "zsh", "dash", "node", "ruby", "perl", "osascript"}
)


@runtime_checkable
class TargetProbe(Protocol):
    """Whether a program or script can be found, and what it really is.

    `locate` answers the only question the engine asks — "can this be found, and
    as what" — so the caller never has to decide between a PATH lookup and a
    filesystem check. That choice belongs to whatever knows about filesystems.
    """

    def locate(self, target: str) -> str | None: ...

    def resolve(self, target: str) -> str: ...


class FilesystemProbe:
    """The real TargetProbe. Constructed at the CLI edge; faked in tests."""

    def locate(self, target: str) -> str | None:
        import shutil

        if "/" in target:
            expanded = os.path.expanduser(target)
            return expanded if os.path.lexists(expanded) else None
        return shutil.which(target)

    def resolve(self, target: str) -> str:
        return os.path.realpath(os.path.expanduser(target))


@dataclass(frozen=True)
class CommandShape:
    """What a hook command actually invokes, once the marker is off.

    `tokens` is the full argv and is the identity — two entries are the same
    invocation only if their whole argv matches. Dropping arguments from that
    comparison made `graphify hook-guard search` and `graphify hook-guard read`
    look like one hook, and prune deleted one of them.
    """

    tokens: tuple[str, ...]
    program: str | None
    script: str | None
    opaque: bool

    @property
    def probeable(self) -> tuple[str, ...]:
        """The targets worth checking: the program, and the script an
        interpreter was handed. Never a data argument — `--log /var/log/x.log`
        names a file the hook creates, not one that must already exist."""
        return tuple(target for target in (self.program, self.script) if target)


OPAQUE_SHAPE = CommandShape(tokens=(), program=None, script=None, opaque=True)


def analyse_command(command: str) -> CommandShape:
    """Decompose `command`, or declare it opaque. Opaque is always safe: it means
    "no claim made", and nothing is ever deleted on the strength of it."""
    clean = config_sync_hooks.strip_marker(command).strip()
    if not clean or any(token in clean for token in SHELL_METACHARACTERS):
        return OPAQUE_SHAPE
    try:
        tokens = tuple(shlex.split(clean))
    except ValueError:
        return OPAQUE_SHAPE
    if not tokens:
        return OPAQUE_SHAPE
    return CommandShape(
        tokens=tokens,
        program=tokens[0],
        script=_script_argument(tokens),
        opaque=False,
    )


def _script_argument(tokens: tuple[str, ...]) -> str | None:
    """The script an interpreter runs, when the program is one we recognise."""
    program_name = os.path.basename(tokens[0])
    is_interpreter = program_name in INTERPRETERS or program_name.startswith("python")
    if not is_interpreter:
        return None
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        return token if _is_absolute(token) else None
    return None


def _is_absolute(token: str) -> bool:
    return token.startswith("/") or token.startswith("~/")


def _classify_target(target: str, probe: TargetProbe) -> str | None:
    """The finding this target justifies, if any.

    Only an absolute path is definitive. A bare program name depends on the PATH
    of whichever shell runs the hook, which is not the PATH of the process
    running the doctor — deleting a hook because *we* could not find `mem` is not
    a defensible basis for an irreversible edit.
    """
    if any(character in target for character in GLOB_CHARACTERS):
        return UNRESOLVABLE
    if probe.locate(target) is not None:
        return None
    if _is_absolute(target):
        return MISSING_TARGET
    if "/" in target:
        return UNRESOLVABLE  # relative: unresolvable without the hook's cwd
    return MISSING_ON_PATH


class ProbingCommandChecker:
    """A `config_sync_hooks.CommandChecker` over a TargetProbe.

    Lives here because analysing a command is this module's job, and satisfies
    the wiring's Protocol structurally — so the dependency still points one way,
    doctor to wiring, with no import back.

    Applies the same rule as prune, for the same reason: only a missing absolute
    path is a real "cannot run". A program merely absent from this PATH, or a
    relative path, or anything with a `$` in it, is not something to refuse to
    wire over.
    """

    def __init__(self, probe: TargetProbe):
        self._probe = probe

    def is_runnable(self, command: str) -> bool:
        shape = analyse_command(command)
        if shape.opaque:
            return True
        return all(
            _classify_target(target, self._probe) != MISSING_TARGET
            for target in shape.probeable
        )


@dataclass(frozen=True)
class Diagnosis:
    site: config_sync_hooks.HookSite
    hook_id: str | None
    findings: tuple[str, ...]
    missing_targets: tuple[str, ...] = ()
    duplicate_of: config_sync_hooks.HookSite | None = None

    @property
    def managed(self) -> bool:
        """True when config-sync wired this entry and may therefore repair it."""
        return self.hook_id is not None

    @property
    def repairable(self) -> bool:
        return any(finding in DEFINITIVE_FINDINGS for finding in self.findings)

    def prunable(self, include_unmanaged: bool) -> bool:
        return self.repairable and (self.managed or include_unmanaged)

    @property
    def definitive_findings(self) -> tuple[str, ...]:
        return tuple(
            finding for finding in self.findings if finding in DEFINITIVE_FINDINGS
        )


def _exact_key(site, shape: CommandShape, probe: TargetProbe):
    """Identity for a definitive duplicate: the same event and matcher running
    the same argv, with absolute paths resolved so two spellings of one file
    unify. Arguments are part of it — that is the whole point."""
    resolved = tuple(
        probe.resolve(token) if _is_absolute(token) else token for token in shape.tokens
    )
    return (site.event, site.matcher, resolved)


def _named_program(shape: CommandShape) -> str | None:
    """The file a command is really about: the script if there is one, else the
    program itself."""
    named = shape.script or shape.program
    return named if named and "/" in named else None


def _script_key(site, shape: CommandShape):
    """Identity for an advisory duplicate: the same event and matcher running a
    script of the same name. Keyed on the name alone, so one guard invoked three
    ways is not read as three hooks."""
    named = _named_program(shape)
    return (
        None if named is None else (site.event, site.matcher, os.path.basename(named))
    )


def diagnose(settings: dict, probe: TargetProbe) -> list[Diagnosis]:
    """Diagnose every hook in `settings`. The first occurrence of a repeated
    invocation is the one kept, so a duplicate always points back at its
    original."""
    diagnoses: list[Diagnosis] = []
    seen_exact: dict[tuple, config_sync_hooks.HookSite] = {}
    seen_script: dict[tuple, config_sync_hooks.HookSite] = {}

    for site in config_sync_hooks.hook_sites(settings):
        hook_id = config_sync_hooks.hook_id_in(site.command)
        shape = analyse_command(site.command)
        if shape.opaque:
            diagnoses.append(Diagnosis(site, hook_id, (OPAQUE,)))
            continue

        findings: list[str] = []
        missing_targets: list[str] = []
        for target in shape.probeable:
            classification = _classify_target(target, probe)
            if classification is None:
                continue
            if classification not in findings:
                findings.append(classification)
            if classification == MISSING_TARGET:
                missing_targets.append(target)

        duplicate_of = None
        exact_key = _exact_key(site, shape, probe)
        script_key = _script_key(site, shape)
        named = _named_program(shape)
        installed_at = probe.resolve(named) if named else None

        if exact_key in seen_exact:
            findings.append(DUPLICATE_COMMAND)
            duplicate_of = seen_exact[exact_key]
        elif script_key is not None and script_key in seen_script:
            previous_site, previous_install = seen_script[script_key]
            # Only a *different* install of the same name is worth reporting.
            # Same file, different arguments — `graphify hook-guard search` and
            # `... read` — is two distinct guards, not a duplicate.
            if previous_install != installed_at:
                findings.append(DUPLICATE_SCRIPT)
                duplicate_of = previous_site

        # Recorded unconditionally. Registering only on the else-branch meant a
        # soft duplicate never entered seen_exact, so a later byte-identical copy
        # of it missed the exact lookup and came back merely advisory — leaving a
        # real duplicate that prune would not touch.
        seen_exact.setdefault(exact_key, site)
        if script_key is not None:
            seen_script.setdefault(script_key, (site, installed_at))

        diagnoses.append(
            Diagnosis(
                site, hook_id, tuple(findings), tuple(missing_targets), duplicate_of
            )
        )
    return diagnoses


@dataclass(frozen=True)
class PruneAction:
    site: config_sync_hooks.HookSite
    reason: str


@dataclass
class PrunePlan:
    actions: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


@dataclass
class PruneOutcome:
    command: str
    ok: bool
    message: str = ""


@dataclass
class PruneResult:
    outcomes: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def plan_hook_pruning(
    diagnoses: list[Diagnosis], include_unmanaged: bool = False
) -> PrunePlan:
    """Pure planner: propose removing only entries with a definitive finding.

    Advisory findings are reported by the doctor and left to the operator — two
    files with one basename may genuinely both be wanted, and guessing wrong
    silently disarms a guard. config-sync removes what it wired unless the
    operator explicitly widens the scope.
    """
    plan = PrunePlan()
    for diagnosis in diagnoses:
        if not diagnosis.repairable:
            continue
        if not diagnosis.managed and not include_unmanaged:
            plan.skipped.append(
                f"{diagnosis.site.command}: not config-sync's — hand-added, left alone"
            )
            continue
        # Only the definitive findings are named: an advisory one riding along on
        # the same entry did not cause the removal and must not be reported as if
        # it had.
        plan.actions.append(
            PruneAction(diagnosis.site, ", ".join(diagnosis.definitive_findings))
        )
    return plan


def execute_prune_plan(
    plan: PrunePlan, host: config_sync_hooks.SettingsHost
) -> PruneResult:
    """Remove each planned entry, collapsing only the groups thereby emptied.

    The plan addresses entries by position, but positions come from the settings
    the *planner* read. Each removal therefore re-checks that the entry still
    sitting there is the one that was diagnosed; if the file moved underneath us,
    that action fails loudly rather than deleting a bystander.
    """
    result = PruneResult(skipped=list(plan.skipped))
    if not plan.actions:
        return result

    settings = host.read_settings()
    touched_groups = set()
    removed_any = False
    # Deepest index first, so removing one entry cannot shift the position of
    # another still to be removed.
    for action in sorted(
        plan.actions,
        key=lambda action: (
            action.site.event,
            action.site.group_index,
            action.site.hook_index,
        ),
        reverse=True,
    ):
        if not _remove_site(settings, action.site):
            result.outcomes.append(
                PruneOutcome(
                    action.site.command,
                    ok=False,
                    message="settings.json changed since it was diagnosed; "
                    "nothing removed for this entry — re-run hooks-doctor",
                )
            )
            continue
        touched_groups.add((action.site.event, action.site.group_index))
        removed_any = True
        result.outcomes.append(
            PruneOutcome(action.site.command, ok=True, message=action.reason)
        )

    if not removed_any:
        return result
    _collapse_empty(settings, touched_groups)
    host.write_settings(settings)
    return result


def _remove_site(settings: dict, site) -> bool:
    """Delete the entry at `site`, but only if it is still the same command."""
    groups = settings.get("hooks", {}).get(site.event)
    if not isinstance(groups, list) or site.group_index >= len(groups):
        return False
    group = groups[site.group_index]
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    if not isinstance(hooks, list) or site.hook_index >= len(hooks):
        return False
    entry = hooks[site.hook_index]
    if not isinstance(entry, dict) or entry.get("command") != site.command:
        return False
    del hooks[site.hook_index]
    return True


def _collapse_empty(settings: dict, touched_groups: set) -> None:
    """Drop the groups THIS run emptied, and any event left with no groups.

    Scoped to the exact groups touched, not merely their events: sweeping every
    empty group also deleted an operator's deliberately-empty placeholder and an
    unrelated event key, neither of which this command was asked to touch.
    """
    hooks_block = settings.get("hooks", {})
    for event in {event for event, _ in touched_groups}:
        groups = hooks_block.get(event)
        if not isinstance(groups, list):
            continue
        kept = [
            group
            for group_index, group in enumerate(groups)
            if (event, group_index) not in touched_groups
            or not isinstance(group, dict)
            or group.get("hooks")
        ]
        if kept:
            hooks_block[event] = kept
        else:
            del hooks_block[event]
