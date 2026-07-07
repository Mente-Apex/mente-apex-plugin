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


class MarketplacePropagator:
    """Exporter for marketplace-sourced plugins (desired-state manifest).

    Classification: a plugin is marketplace-sourced iff the `@marketplace`
    segment of its key is registered in known_marketplaces.json. Only those are
    recorded; the rest are silently deferred to the (unbuilt) local channel.
    Not an Applier — plugin apply is the consent-gated plan/execute pair below.
    """

    name = "marketplace"

    def export(self, context: propagators.SyncContext) -> propagators.ExportResult:
        installed = _read_installed_plugins(context.claude_dir)
        known = _read_known_marketplaces(context.claude_dir)
        marketplaces: dict = {}
        plugins: dict = {}
        for plugin_key, entries in installed.get("plugins", {}).items():
            marketplace_name = plugin_key.split("@", 1)[1] if "@" in plugin_key else ""
            if marketplace_name not in known:
                continue
            entry = entries[0] if isinstance(entries, list) and entries else entries
            version = entry.get("version", "unknown") if isinstance(entry, dict) else "unknown"
            plugin_name = plugin_key.split("@", 1)[0]
            plugins[plugin_key] = {"marketplace": marketplace_name, "name": plugin_name, "version": version}
            marketplaces[marketplace_name] = {"source": known[marketplace_name].get("source")}

        machine_id = propagators._machine_id(context)
        manifest_path = context.repo_dir / "plugins" / f"{machine_id}.json"
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                if existing.get("marketplaces") == marketplaces and existing.get("plugins") == plugins:
                    return propagators.ExportResult(self.name, skipped=[f"plugins/{machine_id}.json (unchanged)"])
            except (json.JSONDecodeError, OSError):
                pass

        record = {
            "machine_id": machine_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "marketplaces": marketplaces,
            "plugins": plugins,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return propagators.ExportResult(self.name, written=[f"plugins/{machine_id}.json"])
