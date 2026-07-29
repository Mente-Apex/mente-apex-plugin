# Answering structural questions (shared)

Every lens spends its first minutes on the same class of question: *where is
this defined, what imports it, what calls it, which way do the dependencies
point?* Answering those by grepping `import` lines and re-listing the tree is
the single largest avoidable cost in an analysis pass — and it gets multiplied
by six under the `code-quality` umbrella.

This file is the shared answer. It is linked, never restated: `analyzer.md`,
`reviewer.md`, and the umbrella's shared index all point here.

## The split that matters

| Question | Kind | Answer it with |
|---|---|---|
| Where is `X` defined? What are its call sites? | **structural** | the graph |
| What imports this module? What does it import? | **structural** | the graph |
| Which class inherits from `Base`? | **structural** | the graph |
| Where is the dependency direction inverted? | **structural** | the graph |
| Repeated type-switches on the same discriminator | **semantic** | `ast-grep` |
| `NotImplementedError` stubs, inline DB construction | **semantic** | `rg` |
| Mock-only assertions, duplicated test bodies | **semantic** | `rg` / read |

**A graph answers "what is connected to what". It cannot answer "what does
this code smell like".** Semantic hunting stays with `ast-grep` (structural
patterns) and ripgrep (literal signatures) — but scoped to the Phase-0 file
list, never as a fresh full-tree sweep.

## Preferred: graphify, when the target repo has it

Many repos here carry a `graphify-out/` knowledge graph. Where one exists it
is strictly cheaper than grep for every structural row above: it returns a
scoped subgraph with `file:line` for each node, so you skip both the tree
listing and the import sweep.

**Detect in Phase 0** — both must hold, or you are on the fallback path:

```sh
command -v graphify                    # the CLI is installed
test -f <target>/graphify-out/graph.json   # this repo has a graph
```

**Check freshness before trusting it.** `graph.json` records
`built_at_commit`; if that differs from `git rev-parse HEAD`, the graph
predates the current tree. Refresh it — `graphify update <path>` is AST-only,
needs no LLM, and costs nothing — or, if you cannot, treat the graph as
advisory and confirm each structural claim against the file before citing it.
**Never cite a `file:line` from a stale graph in a finding**; the reviewer
will fail to verify it and prune a real finding for a bad citation.

**The three commands:**

- `graphify query "<question>"` — a scoped subgraph (BFS from matched nodes).
  The workhorse; use it in place of "list the tree and rank by fan-in".
- `graphify explain "<node>"` — one node and its neighbourhood, in prose.
- `graphify path "<A>" "<B>"` — shortest path between two nodes. This is the
  dependency-direction question: a path from a domain node to an adapter node
  *is* the Dependency-Rule violation, already evidenced.

**Relations available** (what you can actually ask for): `contains` and
`method` give definitions, `calls`/`indirect_call` the call graph,
`imports`/`imports_from` the import graph, `inherits` the type hierarchy,
plus `references` and `uses`. Every node carries `source_file` and
`source_location`, which is your finding's `file:line`.

## Fallback: no graphify, no graph, or a graph you can't trust

**The lens does not fail, stall, or ask.** Absence of a graph is an ordinary
condition — most target repos won't have one. Drop to the ladder the analyzer
contract already describes: list the tree, rank by size and import fan-in,
then hunt with the rubric's signatures via `ast-grep`/ripgrep, scoping every
search to the Phase-0 file list. This is exactly how the lens worked before
graphify existed; it is slower, not worse.

Two rules make the degradation honest:

- **Record it, don't hide it.** One line in the draft's **Coverage** section —
  "no dependency graph available; import direction derived by targeted grep"
  — same as the detect-and-load convention's treatment of a missing language
  reference. Absence is a recorded coverage note, never a silent gap.
- **Never install or build one uninvited.** Running `graphify update` on a
  repo that already has a graph is refreshing a working artifact and is fine.
  Creating a `graphify-out/` in a repo that has none writes a directory the
  user did not ask for — offer, don't do.

## Analysis-phase only

The graph is a snapshot of the tree as it was when built, which makes it an
**analysis-phase artifact** — the same status as the umbrella's shared index.
The apply phase mutates the tree via checkpoint commits, so an implementer
re-derives structure **fresh, per job**, against the live tree and never from
the graph. A graph built before Phase 4 is stale the moment the first job
lands.
