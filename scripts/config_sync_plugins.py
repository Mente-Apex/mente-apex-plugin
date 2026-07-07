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


@dataclass
class PlannedAction:
    verb: str            # add_marketplace | update_marketplace | install_plugin | update_plugin
    target: str          # marketplace name or plugin key
    detail: dict = field(default_factory=dict)


@dataclass
class MarketplacePlan:
    actions: list = field(default_factory=list)     # list[PlannedAction]
    skipped: list = field(default_factory=list)     # list[str] human reasons


def plan_convergence(context: propagators.SyncContext, reader: PluginRegistryReader) -> MarketplacePlan:
    """Pure planner: union all repo manifests, diff against the live registry,
    emit ordered actions (marketplaces first). Never emits an uninstall."""
    desired_marketplaces: dict = {}    # name -> source (or None)
    desired_plugins: dict = {}         # key -> meta
    manifests_dir = context.repo_dir / "plugins"
    if manifests_dir.exists():
        for manifest_path in sorted(manifests_dir.glob("*.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, dict):
                continue
            marketplaces_section = data.get("marketplaces", {})
            plugins_section = data.get("plugins", {})
            if not isinstance(marketplaces_section, dict) or not isinstance(plugins_section, dict):
                continue
            for marketplace_name, marketplace_meta in marketplaces_section.items():
                desired_marketplaces.setdefault(marketplace_name, (marketplace_meta or {}).get("source"))
            for plugin_key, plugin_meta in plugins_section.items():
                desired_plugins[plugin_key] = plugin_meta

    local_marketplaces = reader.known_marketplaces()
    installed = reader.installed_plugins()

    plan = MarketplacePlan()
    unresolved_marketplaces = set()
    for marketplace_name in sorted(desired_marketplaces):
        source = desired_marketplaces[marketplace_name]
        if marketplace_name not in local_marketplaces:
            if source:
                plan.actions.append(PlannedAction("add_marketplace", marketplace_name, {"source": source}))
            else:
                plan.skipped.append(f"marketplace {marketplace_name}: not registered and source unknown")
                unresolved_marketplaces.add(marketplace_name)
                continue
        plan.actions.append(PlannedAction("update_marketplace", marketplace_name))

    for plugin_key in sorted(desired_plugins):
        marketplace_name = plugin_key.split("@", 1)[1] if "@" in plugin_key else ""
        if marketplace_name in unresolved_marketplaces:
            plan.skipped.append(f"plugin {plugin_key}: marketplace {marketplace_name} unavailable")
            continue
        if plugin_key in installed:
            current_version = installed[plugin_key].get("version", "unknown")
            plan.actions.append(PlannedAction("update_plugin", plugin_key, {"current_version": current_version}))
        else:
            plan.actions.append(PlannedAction("install_plugin", plugin_key))
    return plan
