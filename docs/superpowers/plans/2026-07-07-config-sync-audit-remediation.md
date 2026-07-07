# config-sync Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, chosen) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 24 open audit issues (#9–#32) against `scripts/config_sync.py` and the config-sync skill layer — starting with the data-loss/security criticals, backed by the engine's first real test suite.

**Architecture:** Move logic into the engine (testable Python), keep SKILL.md thin. Extract pure functions (settings-merge, path-safety, plugin-meta derivation, section-union) so policy is unit-tested without touching the real `~/.claude`. Tests isolate the filesystem by monkeypatching the engine's path globals to a `tmp_path` `~/.claude`. The big propagation redesign (PS4 cluster) is split into its own gated milestone because it carries genuine design latitude.

**Tech Stack:** Python **3.14.6** via pyenv (pinned in `.python-version`, grounded in `pyproject.toml` `requires-python = ">=3.14"`), pytest 9.x in a repo-local `.venv`, bash skill orchestration.

## Global Constraints

- **Python: 3.14.6 (pyenv), floor `>=3.14` in `pyproject.toml`.** Standing rule: use the newest stable pyenv Python unless a library forces lower. Note: pyenv shims are NOT on the non-interactive shell PATH here — build the venv from `"$(pyenv root)/versions/3.14.6/bin/python3"` and run tests via `.venv/bin/python`.
- **Engine portability:** `config_sync.py` is invoked by skills via `python3 "$ENGINE"`. Keep its syntax broadly compatible (no gratuitous version-locked syntax) so it runs wherever the user's `python3` points; dev/test tooling is the thing pinned to 3.14.
- **DIP first:** the fix is always "pure function does the policy; thin command does the IO." Inject/monkeypatch the path root; never hardcode `Path.home()` inside newly-extracted logic that a test must reach.
- **No abbreviations:** descriptive names in every comprehension/loop var (this is also issue SK6 #31 — the codebase currently violates the user's own global rule).
- **TDD:** red test first, watch it fail, minimal green, refactor, commit. One test at a time.
- **Union-only semantics are intentional** (deletions don't propagate) — preserve that contract; do not "fix" it.
- **Frequent commits:** one commit per task, message ends with `Fixes #<n>` (or `Refs #<n>` when a task only partially closes an issue). Work on a feature branch; do **not** push unless asked.
- **Versions:** `plugin.json` is the canonical plugin version (P10).

---

## File Structure

| File | Responsibility | Touched by |
|---|---|---|
| `scripts/config_sync.py` | Engine — all IO + extracted pure logic | A2,A3,B1,B2,B3,D2,D3,E1,E2 |
| `tests/conftest.py` | Put `scripts/` on path; `claude_home` fixture isolating `~/.claude` | A1 |
| `tests/test_*.py` | The engine test suite (grows per task) | A1,A2,A3,B*,D2,D3,E1 |
| `skills/config-sync/SKILL.md` | Daily sync cycle orchestration | B2,D1,D4,D5 |
| `skills/config-sync-manage/SKILL.md` | status/promote/share | D2,D4,E2 |
| `skills/config-sync-setup/SKILL.md` | first-time setup | D3,D4,F4 |
| `skills/ship/SKILL.md` | commit/PR helper | F2 |
| `skills/menteapex-proposal|onboarding/SKILL.md` | business skills | F3 |
| `.claude-plugin/plugin.json` / `marketplace.json` | version source of truth | F1 |
| `.gitignore` | ignore `.venv/`, `.pytest_cache/` | A1 |

---

## Execution order (importance × compatibility)

1. **Phase A — Foundation + Criticals:** test harness (D7), then C1, C2. *Data loss + security; tests de-risk all that follows.*
2. **Phase B — Merge-engine correctness (Major):** M3, then M4+D9 (one engine `consolidate` command), then M5. *All touch the merge subsystem / Step 3.*
3. **Phase D — Skill-layer correctness & robustness:** SK2, SK5, SK3, SK4, SK7. *Independent, mostly small; SK5 is a live crash.*
4. **Phase E — CQS + dogfooding:** D6 (split export side-effects), then SK6 (rename sweep — done late to avoid churn conflicts).
5. **Phase C — Propagation redesign (PS4 umbrella: PS1, PS2, PS3, D8, SK1):** GATED — needs its own brainstorm + sub-plan. *Highest-value architecture, biggest blast radius, real design choices.*
6. **Phase F — Polish:** P10, P11, P12, P13.

Rationale for C being late despite PS2 being "Major/data-loss": PS1/PS2/PS3 are one entangled redesign (the `Propagator` seam) — doing them piecemeal before the seam exists is throwaway work. The quick, isolated wins (A/B/D/E/F) land first and shrink the surface; C then gets a clean, test-backed base.

---

## Phase A — Foundation + Criticals

### Task A1: Test harness

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_settings_roundtrip.py` (smoke test proving the harness)
- Modify: `.gitignore` (append `.venv/`, `.pytest_cache/`, `tests/__pycache__/`)

**Interfaces:**
- Produces: `import config_sync` works in tests; fixture `claude_home` returns an isolated `CLAUDE_DIR` (`pathlib.Path`) with all engine path globals monkeypatched to it.

- [ ] **Step 1: Pin pyenv 3.14.6, create the venv + install pytest**

```bash
cd /Users/ai/Projects/mente-apex-plugin
pyenv local 3.14.6                              # writes .python-version
PY314="$(pyenv root)/versions/3.14.6/bin/python3"
"$PY314" -m venv .venv                          # shims aren't on PATH; use the binary directly
.venv/bin/python -m pip install -q --upgrade pip pytest
.venv/bin/python --version                      # expect: Python 3.14.6
.venv/bin/python -m pytest --version            # expect: pytest 9.x
```

Also add `pyproject.toml` (`requires-python = ">=3.14"`, pytest `testpaths = ["tests"]`) and commit `.python-version` — the version pin is project ground truth.

- [ ] **Step 2: Write `tests/conftest.py`**

```python
"""Shared fixtures. Isolates the engine from the real ~/.claude."""
import sys
from pathlib import Path

import pytest

# Make `import config_sync` resolve to scripts/config_sync.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import config_sync  # noqa: E402


@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    """Point every engine path global at an isolated throwaway ~/.claude."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    monkeypatch.setattr(config_sync, "HOME", home)
    monkeypatch.setattr(config_sync, "CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(config_sync, "CONFIG_FILE", claude_dir / "config-sync-config.json")
    monkeypatch.setattr(config_sync, "CONFIG_REPO", claude_dir / "config-sync-repo")
    monkeypatch.setattr(config_sync, "PLUGINS_DIR", claude_dir / "plugins")
    monkeypatch.setattr(
        config_sync, "INSTALLED_PLUGINS_FILE", claude_dir / "plugins" / "installed_plugins.json"
    )
    return claude_dir
```

- [ ] **Step 3: Write the smoke test `tests/test_settings_roundtrip.py`**

```python
import config_sync


def test_engine_imports_and_scrubs_env():
    # _clean_settings is pure — no filesystem needed
    cleaned = config_sync._clean_settings('{"model": "opus", "env": {"K": "v"}}')
    assert cleaned == {"model": "opus"}
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 1 passed.

- [ ] **Step 5: Commit** — `test(config-sync): add pytest harness with isolated ~/.claude fixture (Refs #15)`

---

### Task A2: C1 — import must not wipe local secrets/env (#9)

**Files:** Modify `scripts/config_sync.py` (new `_merge_import_settings`, patch `cmd_import`); Test `tests/test_settings_roundtrip.py`.

**Interfaces:**
- Produces: `_merge_import_settings(incoming_scrubbed: dict, existing_local: dict) -> dict` — overlays incoming non-secret keys onto the live local dict, so `env`/secret keys the export omitted survive.

- [ ] **Step 1: Failing test — the flagship round-trip**

```python
def test_import_preserves_local_env_and_apikeyhelper(claude_home, tmp_path):
    settings = claude_home / "settings.json"
    settings.write_text(
        '{"model":"opus","apiKeyHelper":"/bin/helper",'
        '"env":{"ANTHROPIC_API_KEY":"sk-live"},"permissions":{"allow":[]}}'
    )
    # A snapshot as export would produce it: settings.json scrubbed of env/secrets.
    scrubbed = config_sync._clean_settings(settings.read_text())
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(config_sync.json.dumps(
        {"files": {"settings.json": config_sync.json.dumps(scrubbed)}}
    ))

    config_sync.cmd_import(str(snapshot))

    result = config_sync.json.loads(settings.read_text())
    assert result["env"] == {"ANTHROPIC_API_KEY": "sk-live"}   # preserved
    assert result["apiKeyHelper"] == "/bin/helper"             # preserved
    assert result["model"] == "opus"                           # applied from snapshot
```

- [ ] **Step 2: Run — expect FAIL** (`KeyError: 'env'`, because import overwrote with scrubbed content).

Run: `.venv/bin/python -m pytest tests/test_settings_roundtrip.py::test_import_preserves_local_env_and_apikeyhelper -v`

- [ ] **Step 3: Implement `_merge_import_settings` + branch in `cmd_import`**

Add near `_clean_settings`:

```python
def _merge_import_settings(incoming_scrubbed: dict, existing_local: dict) -> dict:
    """Overlay the snapshot's (secret-scrubbed) settings onto the live local file.

    Start from the live local dict so env/apiKeyHelper/secret keys — which the
    export deliberately omits — are never deleted. Incoming non-secret fields win
    (they are the merged network truth). Consistent with the union-only contract:
    import adds/updates, never deletes.
    """
    merged = dict(existing_local)
    for key, value in incoming_scrubbed.items():
        merged[key] = value
    return merged
```

In `cmd_import`, replace the generic write for `settings.json` (currently the loop body around `:263-269`):

```python
        dest = CLAUDE_DIR / rel
        if rel == "settings.json":
            incoming = json.loads(content) if content.strip() else {}
            local_raw = _read(dest)
            existing_local = json.loads(local_raw) if local_raw.strip() else {}
            merged = _merge_import_settings(incoming, existing_local)
            new_content = json.dumps(merged, indent=2, ensure_ascii=False)
            if local_raw == new_content:
                skipped.append(rel)
                continue
            _write(dest, new_content)
            applied.append(rel)
            continue
        existing = _read(dest)
        if existing == content:
            skipped.append(rel)
            continue
        _write(dest, content)
        applied.append(rel)
```

- [ ] **Step 4: Run — expect PASS** (both the round-trip and the smoke test).

- [ ] **Step 5: Add a direct unit test for the pure function**

```python
def test_merge_import_settings_overlays_without_dropping_secrets():
    incoming = {"model": "sonnet", "permissions": {"allow": ["Bash"]}}
    local = {"model": "opus", "env": {"K": "v"}, "apiKeyHelper": "/h"}
    merged = config_sync._merge_import_settings(incoming, local)
    assert merged == {
        "model": "sonnet", "permissions": {"allow": ["Bash"]},
        "env": {"K": "v"}, "apiKeyHelper": "/h",
    }
```

Run: `.venv/bin/python -m pytest tests/ -v` → all pass.

- [ ] **Step 6: Commit** — `fix(config-sync): deep-merge settings on import so local env/secrets survive (Fixes #9)`

---

### Task A3: C2 — path-traversal guard on import + apply-shared (#10)

**Files:** Modify `scripts/config_sync.py` (new `_safe_dest`, use in `cmd_import` and `cmd_apply_shared`); Create `tests/test_path_safety.py`.

**Interfaces:**
- Produces: `_safe_dest(rel: str) -> Optional[Path]` — resolves `rel` under `CLAUDE_DIR`; returns `None` if it escapes (`../`, absolute, symlink-out).

- [ ] **Step 1: Failing test**

```python
import config_sync


def test_import_rejects_traversal_and_absolute_keys(claude_home, tmp_path):
    outside = claude_home.parent.parent / "ESCAPED.txt"
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(config_sync.json.dumps({"files": {
        "../../ESCAPED.txt": "pwned",
        "/tmp/config-sync-abs-escape.txt": "pwned",
        "rules/ok.md": "legit",
    }}))

    config_sync.cmd_import(str(snapshot))

    assert not outside.exists()
    assert not config_sync.Path("/tmp/config-sync-abs-escape.txt").exists()
    assert (claude_home / "rules" / "ok.md").read_text() == "legit"
```

- [ ] **Step 2: Run — expect FAIL** (`ESCAPED.txt` gets written outside).

- [ ] **Step 3: Implement `_safe_dest` and route writes through it**

```python
def _safe_dest(rel: str):
    """Resolve `rel` under CLAUDE_DIR; return None if it escapes the tree."""
    candidate = CLAUDE_DIR / rel
    resolved = candidate.resolve()
    root = CLAUDE_DIR.resolve()
    if resolved == root or resolved.is_relative_to(root):
        return candidate
    return None
```

In `cmd_import`, at the top of the loop body compute `dest = _safe_dest(rel)` and `if dest is None: skipped.append(rel); continue` — then use `dest` (drop the old `dest = CLAUDE_DIR / rel`). In `cmd_apply_shared`, guard both the skills/rules/agents `dest` (around `:587`) and the plugin `install_path` writes (around `:624-631`) the same way, relative to their computed target — for those, assert the resolved dest stays under `CLAUDE_DIR` before `copy2`.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Unit tests for `_safe_dest`** (parametrized: `"rules/x.md"`→ok; `"../x"`→None; `"/etc/x"`→None; `"a/../b.md"`→ok under root).

- [ ] **Step 6: Commit** — `fix(config-sync): reject path traversal / absolute keys on import & apply-shared (Fixes #10)`

---

## Phase B — Merge-engine correctness

### Task B1: M3 — section-union stops fabricating conflicts (#11)

**Files:** Modify `scripts/config_sync.py` (`_section_union` diff branch `:486-521`, add `_line_key`); Create `tests/test_section_union.py`.

**Interfaces:**
- Produces: `_line_key(line: str) -> Optional[str]` — the conflict identity of a line; `None` for list items / blank / non-`key:` lines (which therefore can never conflict, only union).

- [ ] **Step 1: Failing test (the audit repro)**

```python
import config_sync


def test_section_union_unions_list_bullets_without_conflict():
    version_a = "# Prefs\n- Prefers light mode\n"
    version_b = "# Prefs\n- Prefers dark mode\n- Enable telemetry\n"
    merged = config_sync._section_union(version_a, version_b)
    assert "<<<<<<<" not in merged
    assert "- Prefers light mode" in merged
    assert "- Prefers dark mode" in merged
    assert "- Enable telemetry" in merged


def test_section_union_flags_real_keyvalue_contradiction():
    merged = config_sync._section_union("# S\nmodel: opus\n", "# S\nmodel: sonnet\n")
    assert "<<<<<<<" in merged
```

- [ ] **Step 2: Run — expect FAIL** (first test: telemetry bullet swallowed / spurious conflict markers).

- [ ] **Step 3: Implement.** Add helper:

```python
def _line_key(line: str):
    """Conflict identity of a line, or None if it can only be unioned.

    List items (-, *, +, `N.`) and blank lines never conflict — they union.
    Only `key: value` style lines carry an identity that can contradict.
    """
    stripped = line.strip()
    if not stripped or stripped[0] in "-*+" or re.match(r"\d+\.", stripped):
        return None
    match = re.match(r"([^:]+):", stripped)
    return match.group(1).strip() if match else None
```

Replace the contradiction block (`:493-521`) so it keys on `_line_key`, unions everything with no key, and only conflicts on same-key-different-value:

```python
            lines_a = body_a.splitlines()
            lines_b = body_b.splitlines()
            lines_a_stripped = {line.strip() for line in lines_a}
            keys_a = {}
            for line in lines_a:
                key = _line_key(line)
                if key is not None:
                    keys_a.setdefault(key, line)

            merged_lines = list(lines_a)
            conflicts = []
            for line_b in lines_b:
                if not line_b.strip() or line_b.strip() in lines_a_stripped:
                    continue
                key_b = _line_key(line_b)
                if key_b is not None and key_b in keys_a and keys_a[key_b].strip() != line_b.strip():
                    conflicts.append((keys_a[key_b], line_b))
                else:
                    merged_lines.append(line_b)

            if heading != "__preamble__":
                result_parts.append(heading)
            result_parts.append("\n".join(merged_lines))
            for line_a_conflict, line_b_conflict in conflicts:
                result_parts.append(
                    f"\n<<<<<<< Machine A\n{line_a_conflict.strip()}\n"
                    f"=======\n{line_b_conflict.strip()}\n>>>>>>> Machine B\n"
                )
```

- [ ] **Step 4: Run — expect PASS** (both tests + full suite).

- [ ] **Step 5: Commit** — `fix(config-sync): union list bullets, conflict only on key:value contradictions (Fixes #11)`

---

### Task B2: M4 + D9 — timestamp-ordered consolidation in the engine (#12, #17)

**Rationale:** Replace SKILL Step 3's `/tmp` fold-loop (predictable temp files = D9; glob/alphabetical order = M4) with one engine command that reads all snapshots, sorts by `timestamp` ascending (so the most recent is merged last and wins), folds in-process, and writes the consolidated snapshot. Kills both bugs and removes `/tmp` entirely.

**Files:** Modify `scripts/config_sync.py` (extract `_merge_snapshot_files`, add `cmd_consolidate`, register command); Modify `skills/config-sync/SKILL.md` (`:167-194`); Create `tests/test_consolidate.py`.

**Interfaces:**
- Consumes: `_deep_merge_json`, `_smart_merge_text` (unchanged).
- Produces: `_merge_snapshot_files(files_base: dict, files_override: dict) -> tuple[dict, list]` (override wins); `cmd_consolidate(repo_path: str)`; CLI `consolidate <repo>`.

- [ ] **Step 1: Failing test — recency, not filename, decides**

```python
import config_sync


def _snap(machine, ts, model):
    return config_sync.json.dumps({
        "machine_id": machine, "timestamp": ts,
        "files": {"settings.json": config_sync.json.dumps({"model": model})},
    })


def test_consolidate_most_recent_timestamp_wins(tmp_path):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    # 'aaa' is alphabetically first but OLDER; 'zzz' is newer and must win.
    (repo / "machines" / "aaa.json").write_text(_snap("aaa", "2026-01-01T00:00:00+00:00", "opus"))
    (repo / "machines" / "zzz.json").write_text(_snap("zzz", "2026-07-01T00:00:00+00:00", "sonnet"))

    config_sync.cmd_consolidate(str(repo))

    consolidated = config_sync.json.loads((repo / "consolidated" / "snapshot.json").read_text())
    settings = config_sync.json.loads(consolidated["files"]["settings.json"])
    assert settings["model"] == "sonnet"
```

- [ ] **Step 2: Run — expect FAIL** (`cmd_consolidate` undefined).

- [ ] **Step 3: Implement.** Extract the per-file merge from `cmd_merge` into `_merge_snapshot_files(files_base, files_override)` (base first, override wins — reuse the existing key-walk + `_deep_merge_json`/`_smart_merge_text` branch), and refactor `cmd_merge` to call it (DRY). Then:

```python
def cmd_consolidate(repo_path: str):
    """Fold all machine snapshots (+ existing consolidated) into consolidated/snapshot.json.

    Merge order is ascending `timestamp`, so the most recent snapshot is applied
    last and its scalars win. Replaces the SKILL's /tmp fold-loop.
    """
    repo = Path(repo_path)
    consolidated_path = repo / "consolidated" / "snapshot.json"
    machines_dir = repo / "machines"

    snapshots = []
    for snapshot_file in sorted(machines_dir.glob("*.json")):
        snapshots.append(json.loads(snapshot_file.read_text(encoding="utf-8")))
    snapshots.sort(key=lambda snapshot: snapshot.get("timestamp", ""))

    if consolidated_path.exists():
        base_files = json.loads(consolidated_path.read_text(encoding="utf-8")).get("files", {})
    else:
        base_files = {}

    merge_log = []
    for snapshot in snapshots:
        base_files, log = _merge_snapshot_files(base_files, snapshot.get("files", {}))
        merge_log.extend(log)

    result = {
        "machine_id": "consolidated",
        "hostname": "consolidated",
        "platform": platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": base_files,
    }
    consolidated_path.parent.mkdir(parents=True, exist_ok=True)
    consolidated_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"consolidated": str(consolidated_path), "machines": len(snapshots)}))
```

Register in `COMMANDS`: `"consolidate": (cmd_consolidate, 1),`.

- [ ] **Step 4: Run — expect PASS.** Add a second test: markdown light/dark bullets survive a full `consolidate` (integration of B1 through the fold).

- [ ] **Step 5: Rewrite SKILL Step 3** to a single call, deleting the `/tmp/config-sync-*.json` loop:

```bash
## Step 3 — Consolidate all machine snapshots (timestamp-ordered, most-recent-wins)
python3 "$ENGINE" consolidate "$REPO"
```

- [ ] **Step 6: Commit** — `feat(config-sync): engine-side timestamp-ordered consolidate; drop /tmp fold-loop (Fixes #12, Fixes #17)`

---

### Task B3: M5 — structured-first merge; LLM opt-in and capped (#13)

**Rationale:** With M3 fixed, section-union handles common cases. Default to the structured merge; only shell out to `claude -p` when explicitly opted in (`CONFIG_SYNC_LLM_MERGE=1`), and cap total nested invocations per run. Same guard for `cmd_promote`. Eliminates the "nested Claude per differing file inside an active session" cost/latency dead-end by default.

**Files:** Modify `scripts/config_sync.py` (`_smart_merge_text`, `cmd_promote`, add module constants); Create `tests/test_merge_llm_guard.py`.

**Interfaces:**
- Produces: module constants `LLM_MERGE_ENV = "CONFIG_SYNC_LLM_MERGE"`, `MAX_LLM_MERGES = 10`; module counter `_llm_merge_count`.

- [ ] **Step 1: Failing test — default path never shells out**

```python
import config_sync


def test_smart_merge_defaults_to_structured_no_subprocess(monkeypatch):
    called = {"ran": False}
    def _boom(*args, **kwargs):
        called["ran"] = True
        raise AssertionError("subprocess.run must not be called by default")
    monkeypatch.setattr(config_sync.subprocess, "run", _boom)
    monkeypatch.delenv(config_sync.LLM_MERGE_ENV, raising=False)

    merged, strategy = config_sync._smart_merge_text("# S\n- a\n", "# S\n- b\n", context="CLAUDE.md")
    assert called["ran"] is False
    assert strategy == "section-union"
    assert "- a" in merged and "- b" in merged
```

- [ ] **Step 2: Run — expect FAIL** (current code calls `claude -p` when `claude` is on PATH).

- [ ] **Step 3: Implement.** Add constants near the top; gate the LLM branch of `_smart_merge_text` behind `os.environ.get(LLM_MERGE_ENV) == "1"` AND `_llm_merge_count < MAX_LLM_MERGES` (increment on use); otherwise go straight to `_section_union`. Apply the same env gate at the top of `cmd_promote` (when unset, print `{"suggestions": [], "note": "LLM promotion disabled (set CONFIG_SYNC_LLM_MERGE=1)"}` and return).

- [ ] **Step 4: Run — expect PASS.** Add a test: with the env set and `subprocess.run` monkeypatched to return a canned merge, strategy is `"llm-merge"`, and the cap stops calls after `MAX_LLM_MERGES`.

- [ ] **Step 5: Commit** — `fix(config-sync): structured merge by default, cap+opt-in nested claude -p (Fixes #13)`

---

## Phase D — Skill-layer correctness & robustness

### Task D1: SK2 — config-sync allowlists AskUserQuestion (#27)

- [ ] Edit `skills/config-sync/SKILL.md:11` → `allowed-tools: Bash, Read, Write, Edit, AskUserQuestion`. Bump `metadata.version` `0.4.0`→`0.4.1`.
- [ ] Verify: `grep -n allowed-tools skills/config-sync/SKILL.md`.
- [ ] Commit — `fix(config-sync): allowlist AskUserQuestion for its conflict/gate prompts (Fixes #27)`

### Task D2: SK5 — guard plugin-meta derivation against non-cache install paths (#30)

**Files:** Modify `scripts/config_sync.py` (add `_derive_plugin_meta`); Modify `skills/config-sync-manage/SKILL.md:296-321` to call it; Create `tests/test_plugin_meta.py`.

- [ ] **Step 1: Failing test**

```python
import config_sync


def test_derive_plugin_meta_falls_back_when_no_cache_segment():
    entry = {"installPath": "/Users/x/dev/my-plugin", "version": "9.9", "gitCommitSha": "abc"}
    meta = config_sync._derive_plugin_meta("my-plugin@local", entry)
    assert meta["key"] == "my-plugin@local"
    assert meta["marketplace"] == "local"
    assert meta["name"] == "my-plugin"
    assert meta["version"] == "9.9"   # no crash, no StopIteration
```

- [ ] **Step 2: Run — expect FAIL** (`_derive_plugin_meta` undefined).
- [ ] **Step 3: Implement** a single helper that tries the `cache/<marketplace>/<name>/<version>` structure and, when there is no `cache` segment, falls back to splitting `plugin_key` on `@` and the `entry` version:

```python
def _derive_plugin_meta(plugin_key: str, entry: dict) -> dict:
    """Best-effort {key,marketplace,name,version,gitCommitSha} for a plugin.

    Prefers the cache path layout; falls back to the key (`name@marketplace`)
    and the registry entry so a dev/linked install never crashes sharing.
    """
    parts = Path(entry.get("installPath", "")).parts
    marketplace = name = version = None
    if "cache" in parts:
        cache_index = parts.index("cache")
        segments = parts[cache_index + 1:cache_index + 4]
        if len(segments) == 3:
            marketplace, name, version = segments
    if name is None or marketplace is None:
        key_parts = plugin_key.split("@", 1)
        name = key_parts[0]
        marketplace = key_parts[1] if len(key_parts) > 1 else "unknown"
    if version is None:
        version = entry.get("version", "unknown")
    meta = {"key": plugin_key, "marketplace": marketplace, "name": name, "version": version}
    if entry.get("gitCommitSha"):
        meta["gitCommitSha"] = entry["gitCommitSha"]
    return meta
```

- [ ] **Step 4:** Replace the manage SKILL heredoc (`:296-321`) with a call to `python3 "$ENGINE" ...` OR inline `config_sync._derive_plugin_meta`. Simplest: add a tiny CLI `derive-plugin-meta <key>` reading `installed_plugins.json`, or keep the heredoc but import from the engine. Choose: guard inline by importing — `sys.path.insert(0, .../scripts); from config_sync import _derive_plugin_meta`. Bump manage `metadata.version` `0.2.0`→`0.2.1`.
- [ ] **Step 5:** Run suite; commit — `fix(config-sync): guard plugin-meta derivation for non-marketplace installs (Fixes #30)`

### Task D3: SK3 — DRY the secret-scan gate into the engine (#28)

**Files:** Modify `scripts/config_sync.py` (`cmd_scan` gains a `--gate` mode: prints a human block, exits 0 clean / 2 if warnings); Modify both `skills/config-sync/SKILL.md:50-66` and `skills/config-sync-setup/SKILL.md:88-96` to call `python3 "$ENGINE" scan --gate` and branch on exit code; Create `tests/test_scan_gate.py`.

- [ ] Failing test: seed `claude_home/CLAUDE.md` with `AKIA` + a clean file; assert `cmd_scan(gate=True)` returns exit code 2 and prints each `file:line — preview`; clean tree → exit 0.
- [ ] Implement gate mode (reuse existing `scan_patterns`; the "Continue anyway?" **prompt** stays in the skill via AskUserQuestion — only the detection/formatting is DRY'd). Update `main()` to pass the flag.
- [ ] Replace the duplicated bash preview-loops in both skills with the one call.
- [ ] Commit — `refactor(config-sync): single scan --gate used by sync + setup (Fixes #28)`

### Task D4: SK4 — robust engine-path resolution + documented bootstrap (#29)

- [ ] Add a shared resolution snippet to Step 0 of all three config skills (`config-sync`, `config-sync-setup`, `config-sync-manage`):

```bash
ENGINE="${CLAUDE_PLUGIN_ROOT:-}/scripts/config_sync.py"
if [ ! -f "$ENGINE" ]; then
  for candidate in "$HOME/.claude/plugins/cache/"*/mente-apex/*/scripts/config_sync.py; do
    [ -f "$candidate" ] && ENGINE="$candidate" && break
  done
fi
[ -f "$ENGINE" ] || { echo "config_sync.py engine not found — is the mente-apex plugin installed?"; exit 1; }
```

- [ ] Add a "Bootstrap on a fresh machine" note to `README.md`: a new machine must `claude plugin install mente-apex` before `/config-sync-setup` (plugin skills are snapshot-excluded by design).
- [ ] Commit — `fix(config-sync): resolve engine path robustly + document fresh-machine bootstrap (Fixes #29)`

### Task D5: SK7 — remove dead REMOTE var (#32)

- [ ] Delete the unused `REMOTE=$(...)` line in `skills/config-sync/SKILL.md:42`.
- [ ] Commit — `chore(config-sync): drop dead REMOTE variable (Fixes #32)`

---

## Phase E — CQS + dogfooding

### Task E1: D6 — export becomes a pure query; reconcile/prune is explicit (#14)

**Files:** Modify `scripts/config_sync.py` (`cmd_export` no longer writes settings back or `rmtree`s cache; new `cmd_reconcile`); Modify `skills/config-sync/SKILL.md` (call `reconcile` explicitly in Step 1 before export); Create `tests/test_export_pure.py`.

- [ ] Failing test: seed a settings.json with an orphaned plugin + a stale cache dir; run `cmd_export()`; assert settings.json bytes unchanged AND the cache dir still exists (export must not mutate). A separate test asserts `cmd_reconcile()` *does* perform both.
- [ ] Implement: move the write-back + `_prune_stale_plugin_cache` out of `cmd_export` into `cmd_reconcile()`; `cmd_export` still reconciles **in-memory** for the snapshot but touches no disk. `cmd_backup` stays safe (calls the now-pure export). Register `"reconcile": (cmd_reconcile, 0)`.
- [ ] Add `python3 "$ENGINE" reconcile` to SKILL Step 1 before the export line.
- [ ] Commit — `refactor(config-sync): make export a pure query; split reconcile/prune command (Fixes #14)`

### Task E2: SK6 — rename single-letter loop/comprehension vars (#31)

- [ ] Sweep `scripts/config_sync.py` and inline skill Python: `k,v`→`key,value`; `l`→`line`; `p`→`path`; `d`→`directory`; `f`→`file`; `i`(index)→`index`; `part`/`parts` kept; comprehension vars like `[_scrub(i, …) for i in obj]`→`item`, `{l.strip() for l in lines_a}`→`line`. (Some already done in Phases A/B — finish the rest.)
- [ ] Run full suite → all pass (pure rename, behavior identical).
- [ ] Verify gate: `grep -nE '\bfor [a-z] in|\bfor [a-z], [a-z] in| [a-z] for [a-z] in ' scripts/config_sync.py` → no hits.
- [ ] Commit — `style(config-sync): descriptive loop/comprehension names per repo rule (Fixes #31)`

---

## Phase C — Propagation redesign (PS4 umbrella) — GATED

**Closes:** PS4 #25 (root cause), PS1 #22 (marketplace refresh), PS2 #23 (multi-file skill assets dropped — *data loss*), PS3 #24 (local plugin updates frozen), D8 #16 (cache bloat + indent churn), SK1 #26 (export heredoc → engine).

**Why gated (scope check):** This is a distinct subsystem redesign with real design latitude — the `Propagator` seam (`export(local_state)->artifact` / `apply(artifact)->changes`), split into `SnapshotPropagator` / `MarketplacePropagator` / `ContentBundlePropagator`, hash-gated, marketplace-converging. Per writing-plans' scope rule, this gets its **own brainstorm + sub-plan** before code — do not fabricate its steps here.

**Entry criteria:** Phases A–B landed (tests green) so the redesign has a safety net and the engine already owns consolidation.
**First action when unblocked:** `superpowers:brainstorming` on the Propagator seam → then a dedicated `docs/superpowers/plans/2026-…-propagator-seam.md`.

**Interfaces the sub-plan must define (so it stays DIP-clean):**
- `class Propagator(Protocol): def export(self, local_state) -> dict; def apply(self, artifact) -> list[str]`
- `SnapshotPropagator` — files incl. all-file skill bundles (fixes PS2).
- `MarketplacePropagator` — records `{key, marketplace, version}`; on apply runs `claude plugin marketplace update` + `install/update` (fixes PS1).
- `ContentBundlePropagator` — all files, **content-hash-gated** so rebuilds flow (fixes PS3); standard `indent=2` everywhere (fixes D8).
- `export-plugins <repo>` engine command replacing the SKILL heredoc (fixes SK1), symmetric with `apply-shared`.
- The sync cycle iterates an injected list of propagators (open/closed for a 4th channel).

---

## Phase F — Polish

- [ ] **F1 (P10 #18):** Set `.claude-plugin/marketplace.json` version to match `plugin.json` (`0.7.0`); add a one-line comment in README that `plugin.json` is canonical. Commit `Fixes #18`.
- [ ] **F2 (P11 #19):** In `skills/ship/SKILL.md:52,152` replace hardcoded `Co-Authored-By: Claude Opus 4.8` with a model-neutral trailer instruction (use the active model, fall back to `Co-Authored-By: Claude <noreply@anthropic.com>`). Commit `Fixes #19`.
- [ ] **F3 (P12 #20):** In `menteapex-proposal/SKILL.md:42` + `menteapex-onboarding/SKILL.md:126` replace `/Users/ai/Documents/Business/...` with a `BUSINESS_ROOT` (env/config with sensible default) and the hardcoded client "Tomislav" with a neutral sample placeholder. Commit `Fixes #20`.
- [ ] **F4 (P13 #21):** In `config-sync-setup/SKILL.md:71` always warn about public-repo risk (drop the "if the URL looks public" conditional). Commit `Fixes #21`.

---

## Verification (end-to-end)

- **Unit:** `.venv/bin/python -m pytest tests/ -v` — green after every task; the suite is the regression net for C1/C2/M3/M4/M5/D6/SK5.
- **Engine smoke (isolated $HOME, pyenv 3.14):**
  ```bash
  PY314="$(pyenv root)/versions/3.14.6/bin/python3"
  TMPHOME=$(mktemp -d); HOME="$TMPHOME" "$PY314" scripts/config_sync.py status
  HOME="$TMPHOME" "$PY314" scripts/config_sync.py export > /dev/null && echo "export ok, HOME untouched:"; ls -la "$TMPHOME/.claude"
  ```
- **C1 proof:** round-trip a settings.json containing `env.ANTHROPIC_API_KEY` through export→import in a throwaway HOME; assert the key survives (mirrors `test_import_preserves_local_env_and_apikeyhelper`).
- **C2 proof:** import a snapshot with a `../../ESCAPED.txt` key; assert nothing is written outside `~/.claude`.
- **Skill lint:** `grep -rn 'CLAUDE_PLUGIN_ROOT' skills/` shows the guarded fallback; `grep -rn '/tmp/config-sync' skills/` returns nothing after B2.
- **Issue closure:** each commit trailer `Fixes #<n>`; confirm `gh issue list --state open` shrinks as phases land.
```
