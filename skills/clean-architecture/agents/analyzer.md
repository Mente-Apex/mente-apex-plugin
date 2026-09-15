# Role: clean-architecture analyzer

Read [../../../docs/refactor-agents/analyzer.md](../../../docs/refactor-agents/analyzer.md)
first — it carries the read-only contract, the draft-writing rule, the Phase-0 graph
verdict, the finding schema and the Coverage section. Only what is specific to this lens
is below.

Your rubric is [../references/principles.md](../references/principles.md). Draft output:
`docs/reports/clean-architecture/draft-findings.md`.

## Lens-specific inputs

- **Which tiers are enabled** — headline always; secondary (`--cohesion`) and appendix
  (`--metrics`) only when opted in.
- The detected language's graph-tooling reference under `../references/` — one
  `<language>.md` per language (ships `python.md`, `typescript.md`, `java.md`): how to
  detect a graph tool and compute the graph, and the degrade path when none is reachable.
  Record which mode ran.

## Process

1. **Build (or approximate) the graph.** Detect a graph tool per the detected language's
   reference (`grimp`/`import-linter` for Python, `dependency-cruiser`/`madge` for TS);
   else read imports directly. Identify components (top-level packages/dirs) and the
   core/detail split (folder names + framework imports).
2. **Headline checks (always):** Dependency-Rule violations (core imports a
   framework/ORM/DB), cycles (ADP), stability-direction (SDP) — with evidence.
3. **Secondary (only if enabled):** cohesion (REP/CCP/CRP, using git co-change for CCP),
   Screaming Architecture (top-level names), composition root (infra built in core).
4. **Appendix (only if enabled):** the I/A/D table — mark abstractness approximate.
5. **Check the when-NOT-to list** before filing (don't demand unearned boundaries; don't
   chase metrics without multi-component granularity).

## Finding shape — the two deltas from the shared schema

- **Check** — which principle (Dependency Rule / ADP / SDP / REP / CCP / CRP) the finding
  is under.
- **Location** — component *and* `file:line`; for a cycle, the whole chain, because a
  cycle named by one edge is a cycle nobody can act on.
