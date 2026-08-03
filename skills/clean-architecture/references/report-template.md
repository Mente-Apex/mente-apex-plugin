# clean-architecture report template

The reviewer writes
`docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<YYYY-MM-DD>.md` in
exactly this shape. Angle brackets are runtime fill-slots. Field names, the ID
scheme, and the anchor rule are the canonical finding schema defined once in
[docs/report-contract.md](../../../docs/report-contract.md).

Rec IDs are self-describing: `clean-arch/<tier>-<n>`, where `<tier>` ∈ `critical |
major | minor` — so `clean-arch/major-1` reads as "the first Major finding from
the clean-architecture lens" with no legend lookup. The `clean-arch/` prefix makes
every ID globally unique, so the code-quality umbrella carries it verbatim (no
re-prefixing). IDs are permanent once assigned. The tier word records the tier **at
first assignment**; if a finding is later re-tiered, the section heading it sits
under is authoritative and the ID is left unchanged.

**Anchors.** Precede each finding heading with an explicit anchor — the ID with
`/`→`-`, e.g. `<a id="clean-arch-critical-1"></a>` above `#### [clean-arch/critical-1]` —
so the code-quality umbrella's *Full detail* links can jump straight to it (markdown's
auto-generated heading anchors don't handle the `/`).

```markdown
# Clean-architecture Audit — <project> — <YYYY-MM-DD>

## Summary
- Scope: <path>, <N> components, <languages>
- **Analysis mode:** <graph-tool: grimp+import-linter | agent-driven (no graph tool)>
- Tiers run: Headline<, Secondary, Appendix as opted in>
- Findings: <n> Critical, <n> Major, <n> Minor
- Top wins: <the 2–3 that matter most, one line each>

## Findings

### Critical
<a id="clean-arch-critical-1"></a>
#### [clean-arch/critical-1] <short imperative title, e.g. "Lift the ORM out of the use-case layer">
- **Check:** <Dependency Rule | ADP cycle | SDP | cohesion | screaming | composition root>
- **Location:** `package / path:line` <all sites; for a cycle, the component chain>
- **Evidence:** <the offending imports / the metric. No evidence, no finding.>
- **Reader impact:** <why it hurts change-safety/testability — justifies the tier>
- **Proposed change:** <concrete: introduce a port, invert the edge, extract a
  component, move construction to the composition root>
- **Risk:** <Low | Medium | High> — <what could break; never apply High risk>
- **Related:** <lens-overlap rec, e.g. "solid DIP" / "ddd missing port", or none>
- **Tier:** Critical
- **Status:** pending

### Major
<a id="clean-arch-major-1"></a>
#### [clean-arch/major-1] ...

### Minor
<a id="clean-arch-minor-1"></a>
#### [clean-arch/minor-1] ...

## Dependency-rule contract (leave-behind)
<the drafted contract encoding the Dependency-Rule findings, in the detected
language's tool (importlinter.ini for Python, .dependency-cruiser.cjs for JS/TS) —
offered as a CI tripwire; written to docs/reports/clean-architecture/>

## Structural health (appendix — only if --metrics)
<per-component I / A / D table, labelled "abstractness approximate (see the
language reference's caveat)"; call out any Zone-of-Pain / Zone-of-Uselessness
components — context, not findings>

## Coverage & method

Per the plugin's status vocabulary — `ran` / `degraded` / `unverified`, one
line each, and **every `unverified` states its reason**. Absence is data,
never silence.

| What | Status | Note |
|---|---|---|
| <check or measurement> | <ran \| degraded \| unverified> | <rung that ran, what was skipped, or why it did not run> |

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Related findings filed to other lenses: <ids>, or "none"
- Areas not examined: <coverage gaps>

## Outcome

<!-- Written by the orchestrator at Phase 5, once an apply phase has run — the
     persisted run synthesis (applied/deferred/failed ids, suite before/after,
     net diffstat, verification method, residuals). Omit this whole section
     entirely on an audit-only run; format per refactor-workflow.md. Only the
     mechanical, low-risk recs approved at the decision gate reach here —
     architectural moves stay advisory (`agents/implementer.md`). -->

## Apply log

<!-- Appended by the implementer, one line per attempt: -->
<!-- <UTC timestamp> [clean-arch/major-1] applied — suite green (42 passed) — diffstat: 3 files, +120/-85 -->
<!-- <UTC timestamp> [clean-arch/major-2] FAILED — test_x broke, fix attempt failed, reverted -->
```

The `Status:` vocabulary and the Apply-log line format are defined once in the
shared workflow — see [../../../docs/refactor-workflow.md](../../../docs/refactor-workflow.md)
("Status & Apply-log format"). The skeleton above is what the reviewer lays down;
the implementer fills it per that spec.
