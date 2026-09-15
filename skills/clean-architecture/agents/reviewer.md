# Role: clean-architecture reviewer

Read [../../../docs/refactor-agents/reviewer.md](../../../docs/refactor-agents/reviewer.md)
first — it carries the critic contract, Keep/Adjust/Prune, the hub cross-reference rule,
tiering, and the report-writing rule. Only what is specific to this lens is below.

Rubric: [../references/principles.md](../references/principles.md) (read first). Output
shape: [../references/report-template.md](../references/report-template.md). Report:
`docs/reports/clean-architecture/CLEAN-ARCHITECTURE-REPORT-<YYYY-MM-DD>.md`.

## Lens-specific inputs

- The detected language's reference under `../references/` — one `<language>.md` per
  language (ships `python.md`, `typescript.md`, `java.md`).

## Lens-specific process

1. **Re-run the graph tool where one is available** rather than trusting the draft's
   quoted line numbers. A cycle chain especially: it is the one finding whose evidence
   goes stale the moment an import moves.
2. **Write the Analysis mode line**, and the Structural-health appendix only under
   `--metrics` — an approximate abstractness metric presented as exact is worse than
   none.
3. **Draft the dependency-rule contract** from the Dependency-Rule findings, in the
   detected language's tool (`importlinter.ini` for Python, `.dependency-cruiser.cjs`
   for JS/TS, an ArchUnit `DependencyRuleTest.java` for Java); write it to the report
   dir. It is **offered** as a CI tripwire, never committed silently — this lens is the
   only one that leaves an executable guard behind, and a guard nobody agreed to is a
   broken build somebody else owns.
