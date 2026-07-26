"""Root registry for portable hook-command paths (config-sync, issue #65).

Hook `command` strings in settings.json carry machine-absolute paths (e.g.
`python3 /Users/ai/Projects/mente-apex-memory/hooks/protect_brain.py`).
Propagating them verbatim breaks on any machine with a different $HOME or repo
layout. This module rewrites those paths through named ${TOKEN} sentinels on
export and expands them back to local absolute paths on import.

HOME is always present and needs no configuration. Additional named repo roots
are declared per-machine via env vars `CONFIG_SYNC_ROOT_<TOKEN>=<abs path>`
(machine-local, never synced — same philosophy as the scrubbed `env` block).
"""
import copy
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

# Env vars of the form CONFIG_SYNC_ROOT_<TOKEN>=<abs path> declare a named repo
# root on this machine. Machine-local (never synced), so each machine can map the
# same token to wherever it actually cloned the repo.
ROOT_ENV_PREFIX = "CONFIG_SYNC_ROOT_"


@dataclass(frozen=True)
class Root:
    """A named local root: `token` is the portable sentinel name, `path` the
    machine-absolute directory it maps to on this machine."""
    token: str
    path: str


class RootRegistry:
    def __init__(self, roots: list[Root]):
        self._roots = list(roots)

    def portabilize(self, command: str) -> str:
        """Rewrite absolute root prefixes in `command` to ${TOKEN} sentinels.

        Longest path first, so the most specific root (e.g. a repo directory
        nested under HOME) wins over a broader one that also matches.
        """
        for root in self._roots_longest_first():
            # Match the root only at a path boundary — followed by a separator or
            # end of the token — so a sibling like /Users/aimee is never mangled
            # when the root is /Users/ai.
            pattern = re.escape(root.path) + r"(?=/|$|[\s\"'])"
            command = re.sub(pattern, "${" + root.token + "}", command)
        return command

    def localize(self, command: str) -> str:
        """Expand ${TOKEN} sentinels in `command` to this machine's local paths."""
        for root in self._roots:
            command = command.replace("${" + root.token + "}", root.path)
        return command

    def portabilize_settings(self, settings: dict) -> dict:
        """Return a copy of `settings` with every hook command portabilized."""
        return _map_hook_commands(settings, self.portabilize)

    def localize_settings(self, settings: dict) -> dict:
        """Return a copy of `settings` with every hook command localized."""
        return _map_hook_commands(settings, self.localize)

    def _roots_longest_first(self) -> list[Root]:
        return sorted(self._roots, key=lambda root: len(root.path), reverse=True)

    def named_roots(self) -> list[Root]:
        """Declared repo roots (everything except the HOME catch-all) — the
        places wire-hooks scans for hook declarations."""
        return [root for root in self._roots if root.token != "HOME"]


def _map_hook_commands(settings: dict, transform: Callable[[str], str]) -> dict:
    """Return a deep copy of `settings` with `transform` applied to every hook
    `command` string, leaving all other keys untouched. Shape:
    settings["hooks"][<event>] -> [ {"hooks": [ {"command": ...}, ... ]}, ... ]."""
    result = copy.deepcopy(settings)
    for matcher_groups in result.get("hooks", {}).values():
        for matcher_group in matcher_groups:
            for hook in matcher_group.get("hooks", []):
                if isinstance(hook.get("command"), str):
                    hook["command"] = transform(hook["command"])
    return result


def default_registry(home, environ: Mapping[str, str]) -> RootRegistry:
    """Build the registry for this machine: HOME (always) plus any repo roots
    declared via CONFIG_SYNC_ROOT_<TOKEN> env vars. `home` and `environ` are
    injected so the engine and tests stay decoupled from process globals."""
    roots = [Root("HOME", str(home))]
    for env_key, path in environ.items():
        if env_key.startswith(ROOT_ENV_PREFIX) and path:
            roots.append(Root(env_key[len(ROOT_ENV_PREFIX):], path))
    return RootRegistry(roots)
