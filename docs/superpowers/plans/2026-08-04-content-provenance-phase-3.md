# Per-Content Provenance (Rejection Ledger Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an unchanged re-export distinguishable from a deliberate re-add, so a network rejection converges across the fleet without per-machine intervention.

**Architecture:** `SnapshotPropagator.export` stamps one wall-clock time on the whole snapshot, and `cmd_consolidate` passes it as `source_timestamp` for every unit — so untouched content re-exports as "newer than the rejection" and resurrects. This plan gives each addressable unit its own `changed_at`, computed by hashing the unit and comparing against the machine's own previous snapshot (which is already per-machine and conflict-free, so no second document can disagree). One shared iterator, `iter_addressable_units`, is the single enumeration+addressing vocabulary that both the filters and the stamper consume, because a producer/consumer address drift is the exact bug phase 2's final review caught.

**Tech Stack:** Python 3.14, stdlib only (`json`, `hashlib`, `dataclasses`, `datetime`), pytest, black, ruff.

**Design spec:** `docs/superpowers/specs/2026-08-04-config-sync-content-provenance-design.md`. Read §3 (scope), §5 (architecture), §6.1 (nesting), §9 (failure modes) before Task 1.

## Global Constraints

- **No new runtime dependencies.** Stdlib only; the engine runs under `bin/mente-python`, which may resolve to a bare system interpreter.
- **Formatting is not hand-edited.** `uv run black .` owns whitespace; `uv run ruff check --fix .` must be clean before every commit. Lint ruff cannot autofix is a blocker, not a warning. **ruff N818:** every exception class name ends in `Error`.
- **Black rewrites except-tuples.** black 26.5.1 (`target-version = "py314"`) strips the parens from `except (A, B):` when there is no `as` clause, producing the PEP 758 form, and `test_the_repo_is_black_clean` enforces black's output. If you need the parenthesized form, wrap just that `try`/`except` in a narrow `# fmt: off` / `# fmt: on` fence — precedents at `scripts/config_sync_rejections.py` ~line 544 and `scripts/config_sync_hooks.py` ~line 560. Never exclude a whole file. `except (A, B) as name:` is unaffected.
- **Descriptive names throughout**, including in comprehensions and generator expressions — no single-letter or abbreviated loop variables.
- **Timestamps are UTC ISO 8601 strings** (`datetime.now(UTC).isoformat()`). They are compared lexicographically; **do not parse them**.
- **Provenance degrades, rejections fail closed.** Missing or malformed provenance falls back to `snapshot["timestamp"]` and warns. A corrupt rejection ledger still raises `CorruptRejectionLedgerError` and still aborts. Do not make provenance fatal.
- **Scope is a correctness boundary.** `cmd_consolidate` writes SHARED state and gets a network-only policy; local-state writers get the composite. This plan does not change any policy wiring.
- **A rejection withholds; it never deletes.**
- **`filter_settings_keys` stays pure**: it never mutates its input, reads nothing from disk itself, and its own logic never raises.
- **Do not regress the `addresses_of_interest` prefilter** (`scripts/config_sync_rejections.py`). It exists because asking the policy per key, at every depth, per machine, meant ~1000 ledger reads per consolidate. Any new per-unit work must stay outside that hot path or reuse the same bind-once shape.
- **Tests import from `scripts/` directly** — `tests/conftest.py` puts `scripts/` on `sys.path`. `scripts/` is a flat set of sibling scripts, not a package, so cross-script imports inside `scripts/` are **deferred imports inside functions**.
- **Never touch the operator's real `~/.claude` from a test.** `scripts/config_sync.py` computes `HOME`/`CLAUDE_DIR` as module-level globals **at import time**, so monkeypatching `pathlib.Path.home` does not work. Use the `claude_home` fixture in `tests/conftest.py`.
- **Run the suite with** `uv run pytest tests/ -q` from the repo root. Baseline at the start of this plan: **1403 passing**.
- Branch: `feat/config-sync-content-provenance`. Commit after every task.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/config_sync_rejections.py` (modify) | Gains `AddressableUnit` and `iter_addressable_units` — the shared enumeration+addressing vocabulary. `filter_snapshot_files` is refactored to consume it. Gains `SnapshotProvenance` (the reader) and `NullProvenance`. |
| `scripts/config_sync_provenance.py` (create) | The stamper and nothing else. Separate because "when did content change" is a different reason to change than "what is addressable" or "what is rejected". |
| `scripts/config_sync_propagators.py` (modify) | `SnapshotPropagator.__init__` gains an injected stamper; `export` reads its own previous snapshot and writes `provenance`. |
| `scripts/config_sync.py` (modify) | `cmd_consolidate` builds a `SnapshotProvenance` per snapshot and passes it to both filters. |
| `skills/config-sync/SKILL.md` (modify) | Documents automatic convergence and the narrowed meaning of `resolve-rejection`. |
| `tests/test_addressable_units.py` (create) | The iterator's vocabulary, and the drift guard against the filters. |
| `tests/test_content_provenance.py` (create) | The stamper: hashing, carry-forward stability, new/changed units, degradation. |
| `tests/test_provenance_export.py` (create) | Export writes provenance; read-before-write; unreadable previous snapshot. |
| `tests/test_provenance_consolidate.py` (create) | The reader, the filter plumbing, and the mixed-fleet fallback. |
| `tests/test_provenance_convergence.py` (create) | The headline two-machine walks, production-shaped. |

**Out of scope.** `plugin` and `hook-registration` (they pass `""` and cannot resurrect — spec §3). `SnapshotPropagator.apply` (passes `""` deliberately). Deletion propagation. Clock skew. Merging the duplicate composite-policy composition roots.

---

### Task 1: The shared addressable-unit vocabulary

**Files:**
- Modify: `scripts/config_sync_rejections.py`
- Test: `tests/test_addressable_units.py`

**Interfaces:**
- Consumes: `SnapshotFileAddressor`, `SnapshotSectionAddressor`, `SettingsKeyAddressor` (all existing in this module); `config_sync_merge._parse_sections`.
- Produces: `AddressableUnit` (frozen dataclass with `kind: str`, `address: str`, `payload: str`, `source_file: str = ""`, `source: object = None`); `iter_addressable_units(files: dict) -> Iterator[AddressableUnit]`.

This is pure addition — no existing behavior changes in this task.

`payload` is the exact text whose change should bump provenance. `source_file` is the `files` key the unit came from, so a consumer can group by file without parsing an address — parsing an address to recover a field would be exactly the parallel-addressing drift this task exists to prevent. `source` carries what a consumer needs to rebuild: for a section unit it is the `((heading_text, occurrence), heading, body)` triple `_parse_sections` yields, so Task 2's filter can consume this iterator without reimplementing the walk. For other kinds it is `None`.

Enumeration rules, matching what the filters already do:
- every key in `files` yields a `snapshot-file` unit;
- a `.md` file whose content is a `str` additionally yields one `snapshot-section` unit per `_parse_sections` triple;
- `files["settings.json"]`, when it is a `str` that parses to a `dict`, additionally yields one `settings-key` unit per key path at every depth.

Note the asymmetry, and preserve it: `.md` section units come from any `.md` key, while settings-key units come **only** from the literal key `settings.json`. That is exactly what `filter_snapshot_files` and `filter_settings_blob` do today.

- [ ] **Step 1: Write the failing test**

```python
"""The one enumeration+addressing vocabulary that export and the filters share.

A drift between the units this yields and the units the filters query is silent:
every provenance lookup would miss, every unit would fall back to the export
timestamp, and the resurrection fix would stop working with no error at all.
That is the failure this file exists to make loud.
"""

import json

import config_sync_rejections as rejections
from config_sync_rejections import iter_addressable_units

SETTINGS = {
    "permissions": {"defaultMode": "acceptEdits"},
    "model": "opus",
}

FILES = {
    "CLAUDE.md": "# Top\n\n## Alpha\nalpha body\n\n## Beta\nbeta body\n",
    "rules/a.md": "## Only\nonly body\n",
    "settings.json": json.dumps(SETTINGS),
    "keybindings.json": '{"a": 1}',
}


def _units_by_kind(files):
    grouped = {}
    for unit in iter_addressable_units(files):
        grouped.setdefault(unit.kind, []).append(unit)
    return grouped


def test_every_file_key_yields_a_file_unit():
    addresses = {unit.address for unit in _units_by_kind(FILES)["snapshot-file"]}
    assert addresses == set(FILES)


def test_a_markdown_file_yields_one_unit_per_section():
    sections = _units_by_kind(FILES)["snapshot-section"]
    addresses = {unit.address for unit in sections}
    expected = rejections.section_address("rules/a.md", "## Only", 0)
    assert expected in addresses
    assert any('"file": "CLAUDE.md"' in address for address in addresses)


def test_a_repeated_heading_stays_distinct_by_occurrence():
    files = {"CLAUDE.md": "## Notes\nfirst\n\n## Notes\nsecond\n"}
    sections = _units_by_kind(files)["snapshot-section"]
    assert len({unit.address for unit in sections}) == len(sections)


def test_a_non_markdown_file_yields_no_section_units():
    files = {"keybindings.json": '{"a": 1}'}
    assert "snapshot-section" not in _units_by_kind(files)


def test_settings_keys_are_yielded_at_every_depth():
    addresses = {unit.address for unit in _units_by_kind(FILES)["settings-key"]}
    assert rejections.settings_key_address(("permissions",)) in addresses
    assert rejections.settings_key_address(("permissions", "defaultMode")) in addresses
    assert rejections.settings_key_address(("model",)) in addresses


def test_only_the_settings_json_key_yields_settings_units():
    """A different .json file is not settings, however well it parses."""
    files = {"keybindings.json": json.dumps({"permissions": {"defaultMode": "x"}})}
    assert "settings-key" not in _units_by_kind(files)


def test_an_unparseable_settings_blob_yields_no_settings_units():
    files = {"settings.json": "{not json"}
    assert "settings-key" not in _units_by_kind(files)


def test_a_section_unit_carries_the_triple_needed_to_rebuild():
    sections = _units_by_kind({"rules/a.md": "## Only\nonly body\n"})["snapshot-section"]
    (key, heading, body) = sections[0].source
    assert heading == "## Only"
    assert "only body" in body


def test_payloads_differ_when_content_differs():
    first = {"rules/a.md": "## Only\none\n"}
    second = {"rules/a.md": "## Only\ntwo\n"}
    first_payloads = [unit.payload for unit in iter_addressable_units(first)]
    second_payloads = [unit.payload for unit in iter_addressable_units(second)]
    assert first_payloads != second_payloads


def test_the_iterator_and_the_filters_agree_on_every_address():
    """THE DRIFT GUARD. If anyone reimplements addressing on either side, this
    fails loudly instead of provenance silently degrading to the old behaviour."""

    class _RecordingPolicy:
        """Rejects nothing; records every address the filters ask about."""

        def __init__(self):
            self.asked = set()

        def all(self):
            return []

        def is_rejected(self, target, source_timestamp):
            self.asked.add((target.kind, target.address))
            return False

    policy = _RecordingPolicy()
    # `all()` returning [] makes `addresses_of_interest` a prefilter that skips
    # everything, so drive the filters with a policy that has no prefilter.
    policy.all = lambda: (_ for _ in ()).throw(RuntimeError("no prefilter"))

    rejections.filter_snapshot_files(FILES, policy, "")
    rejections.filter_settings_blob(FILES, policy, "")

    iterated = {(unit.kind, unit.address) for unit in iter_addressable_units(FILES)}
    assert iterated == policy.asked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_addressable_units.py -q`
Expected: FAIL with `ImportError: cannot import name 'iter_addressable_units'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/config_sync_rejections.py`:

```python
@dataclass(frozen=True)
class AddressableUnit:
    """One thing a rejection can name, with the text whose change should bump it.

    `payload` is what gets hashed for provenance. `source_file` is the `files`
    key this unit came from, so a consumer groups by file without parsing an
    address apart. `source` carries whatever a consumer needs to rebuild the
    unit -- for a section, the triple `config_sync_merge._parse_sections` yields
    -- so `filter_snapshot_files` can consume this iterator without
    reimplementing the walk. A producer/consumer drift in addressing is silent
    and self-disabling, so there is exactly one enumeration and both sides use it.
    """

    kind: str
    address: str
    payload: str
    source_file: str = ""
    source: object = None


def iter_addressable_units(files: dict):
    """Every unit in a snapshot `files` mapping that a rejection can address.

    Yields file units for every key, section units for every `.md` whose content
    is a string, and settings-key units for the `settings.json` blob at every
    depth. The asymmetry is deliberate and mirrors the filters: sections come
    from any `.md`, settings keys come only from the literal `settings.json` key.
    """
    # Deferred import: config_sync_merge is a sibling script, not a package.
    import config_sync_merge as merge

    file_addressor = SnapshotFileAddressor()
    section_addressor = SnapshotSectionAddressor()
    settings_addressor = SettingsKeyAddressor()

    for file_key, content in files.items():
        payload = content if isinstance(content, str) else json.dumps(
            content, sort_keys=True, ensure_ascii=False
        )
        yield AddressableUnit(
            kind=file_addressor.kind,
            address=file_addressor.identify(file_key),
            payload=payload,
            source_file=file_key,
        )

        if not isinstance(content, str):
            continue

        if file_key.endswith(".md"):
            for key, heading, body in merge._parse_sections(content):
                heading_text, occurrence = key
                yield AddressableUnit(
                    kind=section_addressor.kind,
                    address=section_addressor.identify(
                        (file_key, heading_text, occurrence)
                    ),
                    payload=heading + "\n" + body,
                    source_file=file_key,
                    source=(key, heading, body),
                )

        if file_key == "settings.json":
            try:
                parsed = json.loads(content)
            except ValueError:
                continue
            if not isinstance(parsed, dict):
                continue
            yield from _iter_settings_units(parsed, (), settings_addressor, file_key)


def _iter_settings_units(node: dict, prefix: tuple, addressor, file_key: str):
    """Settings-key units at every depth, in the same order `filter_settings_keys`
    walks them: a key is yielded before its children."""
    for key, value in node.items():
        key_path = prefix + (key,)
        yield AddressableUnit(
            kind=addressor.kind,
            address=addressor.identify(key_path),
            payload=json.dumps(value, sort_keys=True, ensure_ascii=False),
            source_file=file_key,
        )
        if isinstance(value, dict):
            yield from _iter_settings_units(value, key_path, addressor, file_key)
```

Confirm `dataclass` is already imported at the top of the module; the existing `RejectionRecord` uses it, so it is.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_addressable_units.py -q`
Expected: 10 passed

If `test_the_iterator_and_the_filters_agree_on_every_address` fails, **do not adjust the test to match the iterator.** Read what the filters actually ask about and make the iterator agree — the filters are the existing, tested behaviour and they define the vocabulary.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_addressable_units.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_addressable_units.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_addressable_units.py
git commit -m "feat(config-sync): add the shared addressable-unit vocabulary"
```

---

### Task 2: `filter_snapshot_files` consumes the shared iterator

**Files:**
- Modify: `scripts/config_sync_rejections.py` (`filter_snapshot_files`)
- Test: `tests/test_addressable_units.py` (append)

**Interfaces:**
- Consumes: `iter_addressable_units`, `AddressableUnit` from Task 1.
- Produces: no new names. `filter_snapshot_files` keeps its exact signature and return shape.

**This is a behaviour-preserving refactor.** The gate is that every existing test passes untouched.

`filter_snapshot_files` carries a documented non-obvious invariant: a file with **no** rejected section is passed through as the original `content` object, never round-tripped through `_parse_sections`/`rejoin_sections`, because that round-trip is not lossless for a document ending in a bodiless heading (`"## Foo"` and `"## Foo\n"` parse identically, so no rejoin can recover which was the input). Preserve it exactly.

Group the iterator's units by file so the rebuild still has the triples in document order.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_addressable_units.py`:

```python
def test_a_file_with_no_rejected_section_is_passed_through_unchanged():
    """The round-trip invariant: `_parse_sections` is not injective for a
    document ending in a bodiless heading, so an untouched file must never be
    rebuilt. Object identity is the assertion — equality would not catch a
    lossless-looking rebuild."""

    class _RejectsNothing:
        def all(self):
            return []

        def is_rejected(self, target, source_timestamp):
            return False

    content = "## Foo"
    files = {"rules/a.md": content}
    kept, removed = rejections.filter_snapshot_files(files, _RejectsNothing(), "")
    assert kept["rules/a.md"] is content
    assert removed == []


def test_rejecting_one_section_still_rebuilds_the_rest():
    target_address = rejections.section_address("rules/a.md", "## Beta", 0)

    class _RejectsBeta:
        def all(self):
            return []

        def is_rejected(self, target, source_timestamp):
            return target.address == target_address

    files = {"rules/a.md": "## Alpha\nalpha\n\n## Beta\nbeta\n"}
    kept, removed = rejections.filter_snapshot_files(files, _RejectsBeta(), "")
    assert "## Alpha" in kept["rules/a.md"]
    assert "## Beta" not in kept["rules/a.md"]
    assert removed == [target_address]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_addressable_units.py -q`
Expected: both new tests PASS already — they describe current behaviour, and they are the regression gate for the refactor, not a red-first test. Confirm they pass **before** you refactor, so a failure afterwards is unambiguously yours.

- [ ] **Step 3: Rewrite `filter_snapshot_files` to consume the iterator**

Replace the body of `filter_snapshot_files` in `scripts/config_sync_rejections.py`. Keep its docstring verbatim — the round-trip explanation is still correct and still load-bearing.

Group the section units by `unit.source_file` (the field Task 1 put on `AddressableUnit` for exactly this). Never recover the file by parsing an address apart — that would reintroduce the parallel-addressing drift this plan exists to prevent.

```python
def filter_snapshot_files(files: dict, policy, source_timestamp: str) -> tuple:
    """<keep the existing docstring verbatim>"""
    file_addressor = SnapshotFileAddressor()
    section_addressor = SnapshotSectionAddressor()

    sections_by_file: dict = {}
    for unit in iter_addressable_units(files):
        if unit.kind == section_addressor.kind:
            sections_by_file.setdefault(unit.source_file, []).append(unit)

    kept: dict = {}
    removed: list = []

    for file_key, content in files.items():
        file_target = RejectionTarget(
            kind=file_addressor.kind, address=file_addressor.identify(file_key)
        )
        if policy.is_rejected(file_target, source_timestamp):
            removed.append(file_target.address)
            continue

        section_units = sections_by_file.get(file_key)
        if not section_units:
            kept[file_key] = content
            continue

        surviving_sections = []
        any_section_was_rejected = False
        for unit in section_units:
            section_target = RejectionTarget(
                kind=section_addressor.kind, address=unit.address
            )
            if policy.is_rejected(section_target, source_timestamp):
                removed.append(section_target.address)
                any_section_was_rejected = True
                continue
            surviving_sections.append(unit.source)

        if any_section_was_rejected:
            kept[file_key] = rejoin_sections(surviving_sections)
        else:
            kept[file_key] = content

    return kept, removed
```

Note `sections_by_file.get(file_key)` being empty now covers both "not a `.md`" and "content is not a str" — the iterator already made that decision, which is the point of sharing it.

- [ ] **Step 4: Run the full existing coverage**

Run: `uv run pytest tests/test_addressable_units.py tests/test_rejection_addressors.py tests/test_snapshot_propagator_rejections.py tests/test_rejection_cli.py -q`
then: `uv run pytest tests/ -q`
Expected: all pass, 1403 + Task 1's 10 + 2 new. Any failure here is a refactor regression, not a spec question.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_addressable_units.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_addressable_units.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_addressable_units.py
git commit -m "refactor(config-sync): filter snapshot files through the shared iterator"
```

---

### Task 3: The provenance stamper

**Files:**
- Create: `scripts/config_sync_provenance.py`
- Test: `tests/test_content_provenance.py`

**Interfaces:**
- Consumes: `iter_addressable_units` from Task 1.
- Produces: `hash_payload(payload: str) -> str`; `ContentProvenanceStamper` with `stamp(files: dict, previous: dict, now: str) -> dict`.

`stamp` returns the nested map described in spec §6: `{kind: {address: {"changed_at": str, "hash": str}}}`. `previous` is the same shape, from the machine's own last snapshot; `{}` when there is none.

The rule: hash each unit's payload; if `previous` holds the same hash for that kind+address, carry `changed_at` forward **unchanged**; otherwise stamp `now`. Units absent from `files` simply do not appear — no tombstones.

`stamp` is pure: no I/O, no clock read (`now` is injected), input never mutated. That is what makes it trivially testable and is why the clock is a parameter.

- [ ] **Step 1: Write the failing test**

```python
"""When content changed, decided by hashing rather than by the export clock.

The bug this closes: an export is stamped with the time it ran, so unchanged
content re-exports as strictly newer than any rejection and resurrects.
"""

import json

from config_sync_provenance import ContentProvenanceStamper, hash_payload

EARLIER = "2026-07-01T09:00:00+00:00"
NOW = "2026-08-04T09:00:00+00:00"

FILES = {
    "rules/a.md": "## Only\nonly body\n",
    "settings.json": json.dumps({"model": "opus"}),
}


def _stamp(files, previous, now=NOW):
    return ContentProvenanceStamper().stamp(files, previous, now)


def test_a_first_export_stamps_everything_now():
    provenance = _stamp(FILES, {})
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_an_entry_carries_the_hash_that_justified_it():
    provenance = _stamp(FILES, {})
    entry = provenance["snapshot-file"]["rules/a.md"]
    assert entry["hash"] == hash_payload(FILES["rules/a.md"])


def test_unchanged_content_carries_its_original_changed_at_forward():
    first = _stamp(FILES, {}, now=EARLIER)
    second = _stamp(FILES, first, now=NOW)
    assert second["snapshot-file"]["rules/a.md"]["changed_at"] == EARLIER


def test_changed_at_does_not_slide_forward_across_repeated_exports():
    """A sliding stamp passes a single-export test and reintroduces the bug."""
    provenance = _stamp(FILES, {}, now=EARLIER)
    for _ in range(3):
        provenance = _stamp(FILES, provenance, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == EARLIER


def test_changed_content_is_restamped():
    first = _stamp(FILES, {}, now=EARLIER)
    edited = dict(FILES, **{"rules/a.md": "## Only\nedited body\n"})
    second = _stamp(edited, first, now=NOW)
    assert second["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_editing_one_section_leaves_a_sibling_section_untouched():
    """The resurrection fix, at the unit level."""
    two_sections = {"rules/a.md": "## Alpha\nalpha\n\n## Beta\nbeta\n"}
    first = _stamp(two_sections, {}, now=EARLIER)
    edited = {"rules/a.md": "## Alpha\nCHANGED\n\n## Beta\nbeta\n"}
    second = _stamp(edited, first, now=NOW)

    sections = second["snapshot-section"]
    beta = [entry for address, entry in sections.items() if "Beta" in address]
    alpha = [entry for address, entry in sections.items() if "Alpha" in address]
    assert beta[0]["changed_at"] == EARLIER
    assert alpha[0]["changed_at"] == NOW


def test_editing_a_section_does_restamp_the_enclosing_file():
    """Deliberate, per design spec 6.1: for a FILE rejection the unit of intent
    is the file, and any edit to it is a change to the thing that was declined."""
    two_sections = {"rules/a.md": "## Alpha\nalpha\n\n## Beta\nbeta\n"}
    first = _stamp(two_sections, {}, now=EARLIER)
    edited = {"rules/a.md": "## Alpha\nCHANGED\n\n## Beta\nbeta\n"}
    second = _stamp(edited, first, now=NOW)
    assert second["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_a_vanished_unit_simply_drops_out():
    first = _stamp(FILES, {}, now=EARLIER)
    second = _stamp({"settings.json": FILES["settings.json"]}, first, now=NOW)
    assert "rules/a.md" not in second["snapshot-file"]


def test_the_input_is_never_mutated():
    previous = _stamp(FILES, {}, now=EARLIER)
    before = json.dumps(previous, sort_keys=True)
    _stamp(FILES, previous, now=NOW)
    assert json.dumps(previous, sort_keys=True) == before


def test_a_malformed_previous_entry_is_restamped_rather_than_trusted():
    previous = {"snapshot-file": {"rules/a.md": {"hash": "deadbeef"}}}
    provenance = _stamp(FILES, previous, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW


def test_a_previous_map_of_the_wrong_shape_is_ignored():
    provenance = _stamp(FILES, {"snapshot-file": "not a dict"}, now=NOW)
    assert provenance["snapshot-file"]["rules/a.md"]["changed_at"] == NOW
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_content_provenance.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'config_sync_provenance'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/config_sync_provenance.py`:

```python
"""When each addressable unit of a snapshot last changed.

Its own module because this is a different reason to change than "what is
addressable" (`config_sync_rejections.iter_addressable_units`) or "what is
rejected" (the policy). The engine's rejection rule asks whether incoming
content is strictly newer than the rejection; before this existed the only
answer available was the export's wall clock, so unchanged content re-exported
as newer and resurrected.

See docs/superpowers/specs/2026-08-04-config-sync-content-provenance-design.md.
"""

from __future__ import annotations

import hashlib


def hash_payload(payload: str) -> str:
    """A content hash for one addressable unit.

    sha1 is not a security boundary here -- this only answers "is this byte-for-byte
    what we saw last export?", where a collision costs one spurious carry-forward.
    """
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class ContentProvenanceStamper:
    """Decides each unit's `changed_at` by comparing hashes against the machine's
    previous export.

    Pure by construction: `now` is injected rather than read, nothing is written,
    and `previous` is never mutated. One reason to change: the rule for deciding
    that a unit changed.
    """

    def stamp(self, files: dict, previous: dict, now: str) -> dict:
        """The provenance map for `files`, carrying `changed_at` forward wherever
        the content hash still matches `previous`.

        Shape: `{kind: {address: {"changed_at": str, "hash": str}}}`. A unit
        absent from `files` drops out -- deletion propagation belongs to
        `BundleDeletionLedger`, not here.
        """
        # Deferred import: config_sync_rejections is a sibling script, not a package.
        import config_sync_rejections as rejections_module

        stamped: dict = {}
        for unit in rejections_module.iter_addressable_units(files):
            digest = hash_payload(unit.payload)
            carried = _previous_changed_at(previous, unit.kind, unit.address, digest)
            stamped.setdefault(unit.kind, {})[unit.address] = {
                "changed_at": carried if carried is not None else now,
                "hash": digest,
            }
        return stamped


def _previous_changed_at(previous, kind: str, address: str, digest: str):
    """The recorded `changed_at` for this unit if its hash is unchanged, else None.

    Anything malformed answers None, which restamps. Restamping is the
    conservative direction: it can cost one avoidable resurrection, never a
    wrong suppression.
    """
    if not isinstance(previous, dict):
        return None
    by_address = previous.get(kind)
    if not isinstance(by_address, dict):
        return None
    entry = by_address.get(address)
    if not isinstance(entry, dict):
        return None
    if entry.get("hash") != digest:
        return None
    changed_at = entry.get("changed_at")
    return changed_at if isinstance(changed_at, str) and changed_at else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_content_provenance.py -q`
Expected: 11 passed

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_provenance.py tests/test_content_provenance.py
uv run ruff check --fix scripts/config_sync_provenance.py tests/test_content_provenance.py
uv run pytest tests/ -q
git add scripts/config_sync_provenance.py tests/test_content_provenance.py
git commit -m "feat(config-sync): stamp per-unit content provenance by hash"
```

---

### Task 4: Export writes provenance

**Files:**
- Modify: `scripts/config_sync_propagators.py` (`SnapshotPropagator.__init__` at `:840`, `export` at `:848`)
- Test: `tests/test_provenance_export.py`

**Interfaces:**
- Consumes: `ContentProvenanceStamper` from Task 3.
- Produces: `SnapshotPropagator(policy=None, stamper=None)`; the machine snapshot gains a `provenance` key.

The stamper is injected through the constructor, exactly where `policy` already is, defaulting to a real `ContentProvenanceStamper()` when not supplied — the same shape as the existing `policy if policy is not None else NullRejectionPolicy()`.

Export gains a read-before-write: it reads its own `machines/<machine_id>.json` for the previous `provenance` before overwriting it. An unreadable or absent previous snapshot yields `{}`, which restamps everything as `now` — conservative in the safe direction.

`timestamp` keeps its current meaning and value. Do not remove or repurpose it; §8's mixed-fleet fallback depends on it.

- [ ] **Step 1: Write the failing test**

```python
"""Export records when each unit last changed, using its own previous snapshot."""

import json

from config_sync_propagators import SnapshotPropagator, SyncContext

MACHINE_FILE = "machines/{machine_id}.json"


def _context(tmp_path):
    context = SyncContext(claude_dir=tmp_path / "claude", repo_dir=tmp_path / "repo")
    context.claude_dir.mkdir(parents=True, exist_ok=True)
    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nalpha\n\n## Beta\nbeta\n", encoding="utf-8"
    )
    context.repo_dir.mkdir(parents=True, exist_ok=True)
    return context


def _exported(context):
    machine_files = list((context.repo_dir / "machines").glob("*.json"))
    assert len(machine_files) == 1
    return json.loads(machine_files[0].read_text(encoding="utf-8"))


def test_export_writes_a_provenance_map(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    snapshot = _exported(context)
    assert "provenance" in snapshot
    assert "CLAUDE.md" in snapshot["provenance"]["snapshot-file"]


def test_export_keeps_its_own_timestamp_field(tmp_path):
    """The mixed-fleet fallback reads it; it must not be removed or repurposed."""
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    assert _exported(context)["timestamp"]


def test_a_second_export_of_unchanged_content_carries_changed_at_forward(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    first = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]

    SnapshotPropagator().export(context)
    second = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]
    assert second == first


def test_editing_content_restamps_it(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    first = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]

    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nEDITED\n\n## Beta\nbeta\n", encoding="utf-8"
    )
    SnapshotPropagator().export(context)
    second = _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]
    assert second != first


def test_an_unreadable_previous_snapshot_restamps_rather_than_aborting(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    machine_file.write_text("{not json", encoding="utf-8")

    SnapshotPropagator().export(context)
    assert _exported(context)["provenance"]["snapshot-file"]["CLAUDE.md"]["changed_at"]


def test_the_stamper_is_injectable(tmp_path):
    """The seam: a caller can substitute the stamper without touching export."""

    class _FixedStamper:
        def stamp(self, files, previous, now):
            return {"snapshot-file": {"sentinel": {"changed_at": now, "hash": "x"}}}

    context = _context(tmp_path)
    SnapshotPropagator(stamper=_FixedStamper()).export(context)
    assert "sentinel" in _exported(context)["provenance"]["snapshot-file"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provenance_export.py -q`
Expected: FAIL — `test_export_writes_a_provenance_map` gets `KeyError: 'provenance'`.

- [ ] **Step 3: Write minimal implementation**

In `scripts/config_sync_propagators.py`, extend `SnapshotPropagator.__init__`:

```python
    def __init__(self, policy=None, stamper=None):
        # Deferred: sibling scripts, not a package.
        import config_sync_provenance as provenance_module
        import config_sync_rejections as rejections_module

        self._policy = (
            policy if policy is not None else rejections_module.NullRejectionPolicy()
        )
        # Injected like `policy`, so a test can substitute the clock-and-hash
        # decision without reaching into export.
        self._stamper = (
            stamper
            if stamper is not None
            else provenance_module.ContentProvenanceStamper()
        )
```

In `export`, after `machine_id = _machine_id(context)` and before building `snapshot`:

```python
        machines_dir = context.repo_dir / "machines"
        previous_provenance = _previous_provenance(machines_dir, machine_id)
        now = datetime.now(UTC).isoformat()
        snapshot = {
            "machine_id": machine_id,
            "hostname": platform.node(),
            "platform": platform.system(),
            "timestamp": now,
            "files": files,
            "provenance": self._stamper.stamp(files, previous_provenance, now),
        }
```

Reuse the single `now` for both fields so a unit stamped on this run and the
export share one value rather than two clock reads that can differ.

Then remove the now-duplicated `machines_dir = context.repo_dir / "machines"` line
that follows, keeping the `mkdir` and the write exactly as they are.

Add the reader beside the class:

```python
def _previous_provenance(machines_dir, machine_id: str) -> dict:
    """This machine's provenance map from its own last export, or `{}`.

    `{}` restamps everything as now, which can cost one avoidable resurrection
    but can never cause a wrong suppression -- the safe direction. Reading the
    machine's own previous snapshot is what makes a separate index file
    unnecessary, and so makes an index that disagrees with the snapshot
    impossible.
    """
    path = machines_dir / f"{machine_id}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    provenance = payload.get("provenance") if isinstance(payload, dict) else None
    return provenance if isinstance(provenance, dict) else {}
```

Confirm `json`, `datetime` and `UTC` are already imported at the top of
`config_sync_propagators.py`; `export` already calls `datetime.now(UTC)` today.
If `json` is only reached as `config_sync.json`, use that same form here for
consistency with the surrounding code.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_provenance_export.py -q`
Expected: 6 passed

Then: `uv run pytest tests/ -q` — `SnapshotPropagator` has substantial existing coverage in `tests/test_propagators.py`, `tests/test_snapshot_propagator_rejections.py` and `tests/test_propagate_cli.py`, and none of it may regress.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_propagators.py tests/test_provenance_export.py
uv run ruff check --fix scripts/config_sync_propagators.py tests/test_provenance_export.py
uv run pytest tests/ -q
git add scripts/config_sync_propagators.py tests/test_provenance_export.py
git commit -m "feat(config-sync): write per-unit provenance on export"
```

---

### Task 5: The provenance reader and the filter seam

**Files:**
- Modify: `scripts/config_sync_rejections.py` (`filter_snapshot_files`, `filter_settings_keys`, `filter_settings_blob`)
- Test: `tests/test_provenance_consolidate.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `NullProvenance` with `timestamp_for(kind: str, address: str, fallback: str) -> str`; `SnapshotProvenance(provenance_map: dict)` with the same method; all three filters gain a trailing `provenance=None` parameter.

`provenance=None` defaults to `NullProvenance()`, which always returns the `fallback` — so every existing caller and test is unaffected and the new behaviour is opt-in at the call site. This is the same null-object idiom `NullRejectionPolicy` already establishes; do **not** change the `source_timestamp: str` signature.

`SnapshotProvenance.timestamp_for` returns the unit's recorded `changed_at`, or `fallback` when the map has no usable entry. That single fallback rule covers spec §8's mixed fleet and §9's malformed-entry case at once.

- [ ] **Step 1: Write the failing test**

```python
"""Per-unit timestamps reaching the suppression rule."""

import json

import config_sync_rejections as rejections
from config_sync_rejections import (
    NullProvenance,
    RejectionRecord,
    SnapshotProvenance,
    rejection_id_of,
)

REJECTED_AT = "2026-08-01T09:00:00+00:00"
OLDER = "2026-07-01T09:00:00+00:00"
NEWER = "2026-08-03T09:00:00+00:00"
EXPORTED_AT = "2026-08-04T09:00:00+00:00"

FILES = {"rules/a.md": "## Only\nonly body\n"}
ADDRESS = "rules/a.md"


class _LedgerPolicy:
    """A real suppression decision over one in-memory record."""

    def __init__(self):
        self._records = [
            RejectionRecord(
                id=rejection_id_of("snapshot-file", ADDRESS),
                kind="snapshot-file",
                address=ADDRESS,
                scope="network",
                rejected_at=REJECTED_AT,
                machine_id="machine-a",
            )
        ]

    def all(self):
        return list(self._records)

    def is_rejected(self, target, source_timestamp):
        return rejections.CompositeRejectionPolicy(
            [_Store(self._records)]
        ).is_rejected(target, source_timestamp)


class _Store:
    scope = "network"

    def __init__(self, records):
        self._records = records

    def all(self):
        return list(self._records)


def test_the_null_provenance_always_answers_with_the_fallback():
    assert NullProvenance().timestamp_for("snapshot-file", ADDRESS, "fb") == "fb"


def test_a_recorded_changed_at_is_returned():
    provenance = SnapshotProvenance(
        {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
    )
    assert provenance.timestamp_for("snapshot-file", ADDRESS, EXPORTED_AT) == OLDER


def test_a_missing_unit_falls_back():
    provenance = SnapshotProvenance({"snapshot-file": {}})
    assert provenance.timestamp_for("snapshot-file", ADDRESS, EXPORTED_AT) == EXPORTED_AT


def test_a_missing_map_falls_back():
    assert SnapshotProvenance({}).timestamp_for(
        "snapshot-file", ADDRESS, EXPORTED_AT
    ) == EXPORTED_AT


def test_a_malformed_entry_falls_back():
    provenance = SnapshotProvenance({"snapshot-file": {ADDRESS: "not a dict"}})
    assert provenance.timestamp_for("snapshot-file", ADDRESS, EXPORTED_AT) == EXPORTED_AT


def test_unchanged_content_stays_suppressed_despite_a_fresh_export_stamp():
    """THE FIX. Without provenance the fresh export stamp reads as a re-add."""
    provenance = SnapshotProvenance(
        {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
    )
    kept, removed = rejections.filter_snapshot_files(
        FILES, _LedgerPolicy(), EXPORTED_AT, provenance=provenance
    )
    assert ADDRESS not in kept
    assert removed == [ADDRESS]


def test_genuinely_readded_content_overrides_the_rejection():
    provenance = SnapshotProvenance(
        {"snapshot-file": {ADDRESS: {"changed_at": NEWER, "hash": "x"}}}
    )
    kept, removed = rejections.filter_snapshot_files(
        FILES, _LedgerPolicy(), EXPORTED_AT, provenance=provenance
    )
    assert ADDRESS in kept
    assert removed == []


def test_without_provenance_the_old_behaviour_is_unchanged():
    """The mixed-fleet path: an un-upgraded machine resurrects exactly as today."""
    kept, _removed = rejections.filter_snapshot_files(FILES, _LedgerPolicy(), EXPORTED_AT)
    assert ADDRESS in kept


def test_settings_keys_honour_provenance_too():
    settings_files = {"settings.json": json.dumps({"model": "opus"})}
    address = rejections.settings_key_address(("model",))

    class _SettingsPolicy(_LedgerPolicy):
        def __init__(self):
            self._records = [
                RejectionRecord(
                    id=rejection_id_of("settings-key", address),
                    kind="settings-key",
                    address=address,
                    scope="network",
                    rejected_at=REJECTED_AT,
                    machine_id="machine-a",
                )
            ]

    provenance = SnapshotProvenance(
        {"settings-key": {address: {"changed_at": OLDER, "hash": "x"}}}
    )
    kept, removed = rejections.filter_settings_blob(
        settings_files, _SettingsPolicy(), EXPORTED_AT, provenance=provenance
    )
    assert "model" not in json.loads(kept["settings.json"])
    assert removed == [address]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provenance_consolidate.py -q`
Expected: FAIL with `ImportError: cannot import name 'NullProvenance'`

- [ ] **Step 3: Write minimal implementation**

Append the two readers to `scripts/config_sync_rejections.py`:

```python
class NullProvenance:
    """No per-unit provenance: every unit answers with the caller's fallback.

    The default for all three filters, so every pre-provenance caller keeps its
    exact behaviour and the module never branches on a None provenance.
    """

    def timestamp_for(self, kind: str, address: str, fallback: str) -> str:
        return fallback


class SnapshotProvenance:
    """Per-unit `changed_at` read from one machine snapshot's `provenance` map.

    A unit with no usable entry answers with the fallback -- which is the
    snapshot's own export timestamp, i.e. exactly today's behaviour. That one
    rule covers both a machine that has not upgraded yet (no map at all) and a
    map that is present but malformed, deliberately: provenance is an
    optimisation over a fallback that is already correct-if-conservative, so it
    degrades rather than aborting. A corrupt REJECTION ledger still raises.
    """

    def __init__(self, provenance_map: dict):
        self._map = provenance_map if isinstance(provenance_map, dict) else {}

    def timestamp_for(self, kind: str, address: str, fallback: str) -> str:
        by_address = self._map.get(kind)
        if not isinstance(by_address, dict):
            return fallback
        entry = by_address.get(address)
        if not isinstance(entry, dict):
            return fallback
        changed_at = entry.get("changed_at")
        return changed_at if isinstance(changed_at, str) and changed_at else fallback
```

Then thread it through the three filters. Each gains a trailing parameter and
resolves the null object once:

```python
def filter_snapshot_files(files: dict, policy, source_timestamp: str, provenance=None) -> tuple:
```

with, at the top of the body:

```python
    provenance = provenance if provenance is not None else NullProvenance()
```

and each `policy.is_rejected(...)` call site replacing the bare
`source_timestamp` with the per-unit value:

```python
        if policy.is_rejected(
            file_target,
            provenance.timestamp_for(
                file_target.kind, file_target.address, source_timestamp
            ),
        ):
```

Apply the same three changes to the section branch of `filter_snapshot_files`,
to `filter_settings_keys`, and pass `provenance` straight through
`filter_settings_blob` to `filter_settings_keys`.

**Do not disturb the `addresses_of_interest` prefilter** in
`filter_settings_keys`. It runs before any timestamp question and stays exactly
where it is — provenance is only consulted for units that survive the prefilter,
which keeps the hot path unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_provenance_consolidate.py -q`
Expected: 9 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_rejections.py tests/test_provenance_consolidate.py
uv run ruff check --fix scripts/config_sync_rejections.py tests/test_provenance_consolidate.py
uv run pytest tests/ -q
git add scripts/config_sync_rejections.py tests/test_provenance_consolidate.py
git commit -m "feat(config-sync): read per-unit provenance in the rejection filters"
```

---

### Task 6: Consolidate passes provenance

**Files:**
- Modify: `scripts/config_sync.py` (`cmd_consolidate`, the per-snapshot fold at `:952-960`)
- Test: `tests/test_provenance_consolidate.py` (append)

**Interfaces:**
- Consumes: `SnapshotProvenance` from Task 5.
- Produces: no new names.

Only the **incoming snapshot** fold gets provenance. The `base_files` ratchet keeps passing `""`, for the reason its existing comment gives: the prior consolidated snapshot's own timestamp is unknown and older than any live rejection by construction, so `""` already reads as "no fresher intent". Passing provenance there would be meaningless — the consolidated snapshot carries no per-machine provenance map.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_provenance_consolidate.py`:

```python
def _repo_with(tmp_path, provenance, content="## Only\nonly body\n"):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-b.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-b",
                "timestamp": EXPORTED_AT,
                "files": {"rules/a.md": content},
                "provenance": provenance,
            }
        ),
        encoding="utf-8",
    )
    return repo


def _consolidated_files(repo):
    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    return payload["files"]


def _record_network_rejection(repo):
    from config_sync_rejections import SharedRejectionStore

    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-file", ADDRESS),
            kind="snapshot-file",
            address=ADDRESS,
            scope="network",
            rejected_at=REJECTED_AT,
            machine_id="machine-a",
        )
    )


def test_consolidate_honours_a_snapshots_provenance(tmp_path, capsys):
    import config_sync

    repo = _repo_with(
        tmp_path, {"snapshot-file": {ADDRESS: {"changed_at": OLDER, "hash": "x"}}}
    )
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert ADDRESS not in _consolidated_files(repo)


def test_consolidate_lets_a_genuine_readd_through(tmp_path, capsys):
    import config_sync

    repo = _repo_with(
        tmp_path, {"snapshot-file": {ADDRESS: {"changed_at": NEWER, "hash": "x"}}}
    )
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert ADDRESS in _consolidated_files(repo)


def test_a_snapshot_without_provenance_falls_back_to_its_export_stamp(tmp_path, capsys):
    """Mixed fleet: an un-upgraded machine behaves exactly as it does today."""
    import config_sync

    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-b.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-b",
                "timestamp": EXPORTED_AT,
                "files": {"rules/a.md": "## Only\nonly body\n"},
            }
        ),
        encoding="utf-8",
    )
    _record_network_rejection(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert ADDRESS in _consolidated_files(repo)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provenance_consolidate.py -q`
Expected: FAIL — `test_consolidate_honours_a_snapshots_provenance` finds `rules/a.md` still present, because the fold still passes only the export stamp.

- [ ] **Step 3: Write minimal implementation**

In `scripts/config_sync.py`, inside `cmd_consolidate`'s per-snapshot loop, build the reader once per snapshot and pass it to both filters:

```python
    for snapshot in snapshots:
        # Per-unit provenance, when the exporting machine wrote it. A machine
        # that has not upgraded has no map, and every unit falls back to this
        # snapshot's export timestamp -- exactly today's behaviour, per machine.
        snapshot_provenance = rejections_module.SnapshotProvenance(
            snapshot.get("provenance", {})
        )
        incoming_files, incoming_removed = rejections_module.filter_snapshot_files(
            snapshot.get("files", {}),
            policy,
            snapshot.get("timestamp", ""),
            provenance=snapshot_provenance,
        )
        incoming_files, incoming_settings_removed = (
            rejections_module.filter_settings_blob(
                incoming_files,
                policy,
                snapshot.get("timestamp", ""),
                provenance=snapshot_provenance,
            )
        )
```

Leave the `base_files` ratchet calls exactly as they are, `""` and all.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_provenance_consolidate.py -q`
Expected: 12 passed

Then: `uv run pytest tests/ -q` — `cmd_consolidate` is heavily covered; nothing may regress.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync.py tests/test_provenance_consolidate.py
uv run ruff check --fix scripts/config_sync.py tests/test_provenance_consolidate.py
uv run pytest tests/ -q
git add scripts/config_sync.py tests/test_provenance_consolidate.py
git commit -m "feat(config-sync): consolidate against per-unit provenance"
```

---

### Task 7: The convergence walks

**Files:**
- Test: `tests/test_provenance_convergence.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: no code.

Phase 2's final review found a Critical that twelve task-scoped reviews missed, because each side of the defect was correct in isolation. Phase 2 also had to add a remediation task after two of three end-to-end walks turned out unable to fail. This task exists so neither repeats.

Every walk drives the **real** export and the **real** `cmd_consolidate` against a real on-disk repo — no doubles on the path under test.

**The acceptance criterion is falsification.** For the headline walk, comment out the `provenance=snapshot_provenance` argument added in Task 6, observe the walk FAIL, restore it, observe it PASS, and record both outputs in your report. A walk that passes with provenance removed proves nothing.

- [ ] **Step 1: Write the walks**

```python
"""Two machines, one rejection: the convergence the ledger could not reach.

Machine B still holds content machine A rejected. Before per-content provenance,
B's re-export carried a fresh wall-clock stamp, read as a deliberate re-add, and
resurrected the content on every sync. These walks drive the real export and the
real consolidate end to end.
"""

import json

import config_sync
from config_sync_propagators import SnapshotPropagator, SyncContext
from config_sync_rejections import (
    RejectionRecord,
    SharedRejectionStore,
    rejection_id_of,
)

CONTENT = "## Alpha\nalpha body\n\n## Beta\nbeta body\n"
FILE_ADDRESS = "CLAUDE.md"


def _machine(tmp_path, repo, name, content=CONTENT):
    claude_dir = tmp_path / name
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "CLAUDE.md").write_text(content, encoding="utf-8")
    return SyncContext(claude_dir=claude_dir, repo_dir=repo)


def _reject_file(repo, address=FILE_ADDRESS, rejected_at="2026-08-02T09:00:00+00:00"):
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-file", address),
            kind="snapshot-file",
            address=address,
            scope="network",
            rejected_at=rejected_at,
            machine_id="machine-a",
        )
    )


def _consolidated(repo):
    return json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )["files"]


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidated").mkdir(parents=True)
    return repo


def test_an_unchanged_reexport_no_longer_resurrects_rejected_content(tmp_path, capsys):
    """THE HEADLINE. This fails without provenance -- it is the bug."""
    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")

    SnapshotPropagator().export(context)          # B holds the content
    _reject_file(repo)                            # A rejects it
    SnapshotPropagator().export(context)          # B re-exports, untouched
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert FILE_ADDRESS not in _consolidated(repo)


def test_a_genuine_readd_still_overrides_the_rejection(tmp_path, capsys):
    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")

    SnapshotPropagator().export(context)
    _reject_file(repo)
    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nDELIBERATELY REWRITTEN\n", encoding="utf-8"
    )
    SnapshotPropagator().export(context)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert FILE_ADDRESS in _consolidated(repo)


def test_convergence_holds_across_repeated_syncs(tmp_path, capsys):
    """Carry-forward at the walk level: a sliding changed_at would resurrect on
    the second or third sync, not the first."""
    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")

    SnapshotPropagator().export(context)
    _reject_file(repo)
    for _ in range(3):
        SnapshotPropagator().export(context)
        config_sync.cmd_consolidate(str(repo))
        capsys.readouterr()
        assert FILE_ADDRESS not in _consolidated(repo)


def test_editing_a_sibling_section_does_not_resurrect_a_rejected_section(
    tmp_path, capsys
):
    """The finer-grained case the whole-file mtime approach could not express."""
    from config_sync_rejections import section_address

    repo = _repo(tmp_path)
    context = _machine(tmp_path, repo, "machine-b")
    beta_address = section_address("CLAUDE.md", "## Beta", 0)

    SnapshotPropagator().export(context)
    SharedRejectionStore(repo, "machine-a").record(
        RejectionRecord(
            id=rejection_id_of("snapshot-section", beta_address),
            kind="snapshot-section",
            address=beta_address,
            scope="network",
            rejected_at="2026-08-02T09:00:00+00:00",
            machine_id="machine-a",
        )
    )
    (context.claude_dir / "CLAUDE.md").write_text(
        "## Alpha\nEDITED ALPHA\n\n## Beta\nbeta body\n", encoding="utf-8"
    )
    SnapshotPropagator().export(context)
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    merged = _consolidated(repo)["CLAUDE.md"]
    assert "EDITED ALPHA" in merged
    assert "beta body" not in merged


def test_an_unupgraded_machine_still_resurrects_until_it_upgrades(tmp_path, capsys):
    """Mixed fleet, end to end: the fallback is per-machine, not fleet-wide."""
    repo = _repo(tmp_path)
    (repo / "machines").mkdir(parents=True, exist_ok=True)
    (repo / "machines" / "machine-old.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-old",
                "timestamp": "2026-08-09T09:00:00+00:00",
                "files": {"CLAUDE.md": CONTENT},
            }
        ),
        encoding="utf-8",
    )
    _reject_file(repo)

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    assert FILE_ADDRESS in _consolidated(repo)
```

- [ ] **Step 2: Run the walks**

Run: `uv run pytest tests/test_provenance_convergence.py -q`
Expected: 5 passed

If a walk fails, that is a real integration defect in Tasks 1-6. Investigate and report it — do **not** weaken the assertion to make it pass.

- [ ] **Step 3: Perform the falsification check**

In `scripts/config_sync.py`, temporarily remove the `provenance=snapshot_provenance` argument from the `filter_snapshot_files` call added in Task 6.

Run: `uv run pytest tests/test_provenance_convergence.py -q`
Expected: `test_an_unchanged_reexport_no_longer_resurrects_rejected_content`,
`test_convergence_holds_across_repeated_syncs` and
`test_editing_a_sibling_section_does_not_resurrect_a_rejected_section` all FAIL.

Restore the argument. Run again; expected: 5 passed. Record both outputs in your report.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -q`
Then confirm `git diff scripts/` is empty — the falsification check must leave no trace.

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black tests/test_provenance_convergence.py
uv run ruff check --fix tests/test_provenance_convergence.py
uv run pytest tests/ -q
git add tests/test_provenance_convergence.py
git commit -m "test(config-sync): walk a rejection to convergence across two machines"
```

---

### Task 8: Warn when provenance degrades

**Files:**
- Modify: `scripts/config_sync_propagators.py` (`SnapshotPropagator.export`, `_previous_provenance`)
- Modify: `scripts/config_sync.py` (`cmd_consolidate`)
- Test: `tests/test_provenance_export.py` (append), `tests/test_provenance_consolidate.py` (append)

**Interfaces:**
- Consumes: `_previous_provenance` from Task 4; `SnapshotProvenance` from Task 5.
- Produces: `_previous_provenance(machines_dir, machine_id) -> tuple[dict, list]` — the map and a list of warning strings. The consolidated snapshot gains a `provenance_warnings` key.

Spec §9 requires the degraded paths to **warn**, not merely fall back. A silent fallback is indistinguishable from provenance working, which is the same silent-degradation shape §9 names as the nastiest failure mode.

Use the existing channels rather than inventing one: `ExportResult.warnings` already exists and is already populated at three sites in this module. On the consolidate side, the result dict already carries `merge_log` and `rejected`, so a sibling `provenance_warnings` key fits the established shape and reaches stdout with the rest.

Warn on exactly two conditions, both from §9:
- **export** — the previous snapshot exists but does not parse, so everything restamps as `now`. An *absent* previous snapshot is a first export, which is normal and must NOT warn.
- **consolidate** — a snapshot carries a `provenance` key that is not a dict. A snapshot with no `provenance` key at all is an un-upgraded machine, which is the expected mixed-fleet path and must NOT warn, or every sync warns until the whole fleet upgrades.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_provenance_export.py`:

```python
def test_a_first_export_does_not_warn(tmp_path):
    """No previous snapshot is normal, not degraded."""
    context = _context(tmp_path)
    result = SnapshotPropagator().export(context)
    assert result.warnings == []


def test_an_unreadable_previous_snapshot_warns(tmp_path):
    context = _context(tmp_path)
    SnapshotPropagator().export(context)
    machine_file = list((context.repo_dir / "machines").glob("*.json"))[0]
    machine_file.write_text("{not json", encoding="utf-8")

    result = SnapshotPropagator().export(context)
    assert any("provenance" in warning for warning in result.warnings)
```

Append to `tests/test_provenance_consolidate.py`:

```python
def test_a_snapshot_without_provenance_does_not_warn(tmp_path, capsys):
    """The mixed-fleet path is expected, not degraded — warning here would fire
    on every sync until the entire fleet upgrades."""
    import config_sync

    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    (repo / "machines" / "machine-b.json").write_text(
        json.dumps(
            {
                "machine_id": "machine-b",
                "timestamp": EXPORTED_AT,
                "files": {"rules/a.md": "## Only\nonly body\n"},
            }
        ),
        encoding="utf-8",
    )

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert payload["provenance_warnings"] == []


def test_a_malformed_provenance_map_warns_and_names_the_machine(tmp_path, capsys):
    import config_sync

    repo = _repo_with(tmp_path, "not a dict")

    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()

    payload = json.loads(
        (repo / "consolidated" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert any("machine-b" in warning for warning in payload["provenance_warnings"])


def test_a_malformed_provenance_map_still_consolidates(tmp_path, capsys):
    """Degrades, never aborts — unlike a corrupt rejection ledger."""
    import config_sync

    repo = _repo_with(tmp_path, "not a dict")
    config_sync.cmd_consolidate(str(repo))
    capsys.readouterr()
    assert "rules/a.md" in _consolidated_files(repo)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_provenance_export.py tests/test_provenance_consolidate.py -q`
Expected: FAIL — `test_an_unreadable_previous_snapshot_warns` finds `warnings == []`, and the consolidate tests raise `KeyError: 'provenance_warnings'`.

- [ ] **Step 3: Write minimal implementation**

In `scripts/config_sync_propagators.py`, widen `_previous_provenance` to report:

```python
def _previous_provenance(machines_dir, machine_id: str) -> tuple:
    """This machine's provenance map from its own last export, plus any warnings.

    Returns `(map, warnings)`. An ABSENT previous snapshot is a first export and
    is silent -- warning there would fire on every new machine. An unreadable one
    is genuinely degraded: everything restamps as now, which can cost one
    avoidable resurrection, and the operator should know why.
    """
    path = machines_dir / f"{machine_id}.json"
    if not path.exists():
        return {}, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [
            f"{path.name} does not parse ({exc}); re-stamping all content "
            "provenance as now, which may re-add content rejected elsewhere"
        ]
    provenance = payload.get("provenance") if isinstance(payload, dict) else None
    if provenance is None:
        return {}, []
    if not isinstance(provenance, dict):
        return {}, [f"{path.name} has a malformed provenance map; re-stamping"]
    return provenance, []
```

Update `export`'s call site to unpack both and carry the warnings into its result:

```python
        previous_provenance, provenance_warnings = _previous_provenance(
            machines_dir, machine_id
        )
```

and, on the `ExportResult` it returns:

```python
        return ExportResult(
            self.name,
            written=[f"machines/{machine_id}.json"],
            warnings=provenance_warnings,
        )
```

In `scripts/config_sync.py`'s `cmd_consolidate`, collect per-snapshot warnings
where the reader is built:

```python
    provenance_warnings = []
```

before the fold, then inside it:

```python
        raw_provenance = snapshot.get("provenance")
        if raw_provenance is not None and not isinstance(raw_provenance, dict):
            # A machine with NO provenance key is simply un-upgraded — the
            # expected mixed-fleet path, and silent. A malformed one is a real
            # defect worth naming, but still not fatal: falling back costs one
            # avoidable prompt, while aborting would halt the whole fleet.
            provenance_warnings.append(
                f"{snapshot.get('machine_id', 'unknown')} has a malformed "
                "provenance map; falling back to its export timestamp"
            )
        snapshot_provenance = rejections_module.SnapshotProvenance(
            raw_provenance if isinstance(raw_provenance, dict) else {}
        )
```

and add the key to the result dict beside `rejected`:

```python
        "provenance_warnings": provenance_warnings,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_provenance_export.py tests/test_provenance_consolidate.py -q`
Expected: 8 + 15 passed

Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black scripts/config_sync_propagators.py scripts/config_sync.py tests/test_provenance_export.py tests/test_provenance_consolidate.py
uv run ruff check --fix scripts/config_sync_propagators.py scripts/config_sync.py tests/test_provenance_export.py tests/test_provenance_consolidate.py
uv run pytest tests/ -q
git add scripts/config_sync_propagators.py scripts/config_sync.py tests/test_provenance_export.py tests/test_provenance_consolidate.py
git commit -m "feat(config-sync): warn when content provenance degrades"
```

---

### Task 9: Document automatic convergence

**Files:**
- Modify: `skills/config-sync/SKILL.md`
- Test: `tests/test_rejection_skill_docs.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: no code.

Documentation only. Do not change production code. If the docs cannot be written truthfully without a code change, stop and report it.

What changed for an operator, and what did not:

- A network rejection now converges on its own. A machine that still holds the content but has not edited it stops re-adding it, so `resolve-rejection` is no longer required for correctness.
- `resolve-rejection` still exists, with a narrower meaning: the content is still on that machine's disk, and a rejection withholds rather than deletes. `remove` clears it locally; `keep` still lets one machine overrule the network.
- Editing content genuinely re-adds it. That is the intended escape hatch — an operator who wants rejected content back edits it, or runs `unreject`.
- Per spec §6.1: editing any part of a file re-adds a whole-file rejection, because for a file rejection the unit of intent is the file. Editing one section does **not** re-add a different rejected section in the same file.
- A machine running an older engine keeps the old behaviour until it upgrades. No flag day.

Follow how the existing SKILL.md documents the rejection kinds and extend that shape. Match its voice.

`tests/test_rejection_skill_docs.py` already defines a module-level `SKILL` path and imports `mutation_gate_prose`; reuse both. Scope the assertion to a section with `mutation_gate_prose.extract_section` rather than asserting a substring against the whole file — a whole-file substring test passes while the behaviour it describes is broken, which phase 2's review demonstrated. Note the existing `STEP_5` constant's comment: section markers carry **no** leading `##`, because `mutation_gate_prose._locate` wraps the marker in `\b` and `#` has no word boundary before it.

- [ ] **Step 1: Read the existing rejection documentation**

Read `skills/config-sync/SKILL.md` in full, and the Step 3/Step 4 callouts phase 2 added for the `--force` guard and the scope asymmetry. Match their voice and shape.

- [ ] **Step 2: Write the documentation**

Add a callout covering the five points above, placed where the rejection lifecycle is described — next to where `resolve-rejection` is currently explained, since that command's meaning is what changes.

- [ ] **Step 3: Append a doc test**

```python
STEP_4E_CONVERGENCE = "Step 4 — Backup, then apply through the propagator seam"


def test_the_skill_documents_that_convergence_no_longer_needs_resolve_rejection():
    """Scoped to the section, not the whole file: a whole-file substring test
    passes even when the behaviour it describes is broken."""
    section = mutation_gate_prose.extract_section(
        SKILL.read_text(encoding="utf-8"), STEP_4E_CONVERGENCE
    )
    assert "resolve-rejection" in section
    assert "converge" in section.lower()
```

Adapt `STEP_4E_CONVERGENCE` to the exact heading text of wherever you placed the
callout, minus any leading `##`. If `extract_section` cannot locate it, the
marker is wrong — fix the marker, not the test's intent.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_rejection_skill_docs.py -q`
Then: `uv run pytest tests/ -q`

- [ ] **Step 5: Format, lint, commit**

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run black tests/test_rejection_skill_docs.py
uv run ruff check --fix tests/test_rejection_skill_docs.py
uv run pytest tests/ -q
git add skills/config-sync/SKILL.md tests/test_rejection_skill_docs.py
git commit -m "docs(config-sync): document automatic rejection convergence"
```

---

## Verification

From a clean checkout of the branch:

```bash
cd /Users/ai/Projects/mente-apex-plugin
uv run pytest tests/ -q          # expect 1403 + ~52 new, no failures
uv run black --check .
uv run ruff check .
```

Then confirm the headline behaviour by hand, against a scratch repo:

```bash
ENGINE=/Users/ai/Projects/mente-apex-plugin/scripts/config_sync.py
# 1. Export a machine holding some content.
# 2. reject <repo> snapshot-file <that file> --scope network
# 3. Export the SAME machine again, without editing anything.
# 4. consolidate.
python3 - <<'PY'
import json
snapshot = json.load(open("consolidated/snapshot.json"))
present = "<that file>" in snapshot["files"]
print("STILL PRESENT - FAIL" if present else "withheld - PASS")
PY
```

Inspect `.files` rather than grepping the raw snapshot: `cmd_consolidate` writes the
`"rejected"` audit trail into the same document and each address contains the rejected
file's own name, so a naive grep matches the audit trail and reports a false failure.
Phases 1 and 2 carry the same note for the same reason.
