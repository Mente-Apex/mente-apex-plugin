"""Plugin propagation for config-sync — the marketplace desired-state channel.

DIP: the planner depends only on PluginRegistryReader (pure file reads);
the executor depends only on PluginInstaller (the sole subprocess boundary).
ClaudePluginHost is the injected concretion implementing both; tests fake them.
Dependency direction is one-way: this module imports config_sync_propagators,
never the reverse.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

import config_sync_propagators as propagators


def _read_installed_plugins(claude_dir: Path) -> dict:
    path = claude_dir / "plugins" / "installed_plugins.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_known_marketplaces(claude_dir: Path) -> dict:
    path = claude_dir / "plugins" / "known_marketplaces.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@runtime_checkable
class PluginRegistryReader(Protocol):
    def installed_plugins(self) -> dict: ...      # {key: entry_dict}

    def known_marketplaces(self) -> dict: ...     # {name: {"source": {...}}}


class ClaudePluginHost:
    """Real host: reads the two registry JSON files; shells out to `claude plugin`
    for mutations (added in Task 5). Injected via the CLI wrappers; faked in tests."""

    def __init__(self, context: propagators.SyncContext):
        self._context = context

    def installed_plugins(self) -> dict:
        raw = _read_installed_plugins(self._context.claude_dir)
        flattened = {}
        for plugin_key, entries in raw.get("plugins", {}).items():
            entry = entries[0] if isinstance(entries, list) and entries else entries
            if isinstance(entry, dict):
                flattened[plugin_key] = entry
        return flattened

    def known_marketplaces(self) -> dict:
        return _read_known_marketplaces(self._context.claude_dir)
