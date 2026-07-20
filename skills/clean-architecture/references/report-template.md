# clean-architecture report template

The reviewer writes
`docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<YYYY-MM-DD>.md` in
exactly this shape. IDs `C1,C2,…` / `M1,…` / `N1,…`, permanent once assigned.
Angle brackets are runtime fill-slots.

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
#### [C1] <short imperative title, e.g. "Lift the ORM out of the use-case layer">
- **Check:** <Dependency Rule | ADP cycle | SDP | cohesion | screaming | composition root>
- **Location:** `package / path:line` <all sites; for a cycle, the component chain>
- **Evidence:** <the offending imports / the metric. No evidence, no finding.>
- **Impact:** <why it hurts change-safety/testability — justifies the tier>
- **Fix:** <concrete: introduce a port, invert the edge, extract a component,
  move construction to the composition root>
- **Cross-ref:** <lens-overlap rec, e.g. "solid DIP" / "ddd missing port", or none>
- **Tier:** Critical
- **Status:** pending

### Major
#### [M1] ...

### Minor
#### [N1] ...

## import-linter contract (leave-behind)
<the drafted importlinter.ini encoding the Dependency-Rule findings — offered as a
CI tripwire; written to docs/reports/clean-architecture/importlinter.ini>

## Structural health (appendix — only if --metrics)
<per-component I / A / D table, labelled "abstractness approximate in Python";
call out any Zone-of-Pain / Zone-of-Uselessness components — context, not findings>

## Reviewer notes
- Draft findings pruned as false positives: <finding → reason>, or "none"
- Cross-references filed to other lenses: <ids>, or "none"
- Areas not examined: <coverage gaps>
```
