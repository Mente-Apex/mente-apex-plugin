# clean-architecture in Python — tooling & metrics

The headline checks want the real import graph. Use a tool when one is reachable;
**degrade gracefully** when not — fall back to reading imports directly.

## Detect a graph tool (no hard install)

Try, in order, whatever the environment offers — a project-local install
(`python -c "import grimp"`), then a runner (`uvx import-linter`, `pipx run
import-linter`). Record which path succeeded. If **none** is reachable, switch to
the **degrade path** below and state "agent-driven (no graph tool)" in the report.

## `grimp` — the import graph, cycles, and Instability

Compute Instability (the SDP metric) using fan-in and fan-out:

A component is a sub-package, not a single module — so fan-in/fan-out must
aggregate every module in the sub-tree, not just the `__init__`. `grimp`'s direct
-import methods work on one module node, so gather each component's descendants and
count only the edges that cross a component boundary:

```python
import grimp

top_package = "your_top_package"
graph = grimp.build_graph(top_package)
components = graph.find_children(top_package)        # the sub-packages = components

def modules_of(component):                            # the component node + its whole sub-tree
    return {component} | graph.find_descendants(component)

def owning_component(module):                         # map any module back to its component
    for component in components:
        if module == component or module.startswith(component + "."):
            return component
    return None                                       # external / top-level module

for component in sorted(components):
    efferent_components, afferent_components = set(), set()
    for module in modules_of(component):
        for imported_module in graph.find_modules_directly_imported_by(module):
            owner = owning_component(imported_module)
            if owner is not None and owner != component:      # skip intra-component edges
                efferent_components.add(owner)
        for importing_module in graph.find_modules_that_directly_import(module):
            owner = owning_component(importing_module)
            if owner is not None and owner != component:
                afferent_components.add(owner)
    fan_out, fan_in = len(efferent_components), len(afferent_components)  # Ce, Ca
    denominator = fan_in + fan_out
    # isolated component (no cross-component edges) → treated as maximally stable (I=0)
    instability = fan_out / denominator if denominator else 0.0           # SDP metric
    print(component, round(instability, 2))
```
Cycles (ADP): `grimp` has **no** built-in cycle finder —
`find_illegal_dependencies_for_layers(...)` checks a *layered* contract, not cycles.
Build the component edge set from the fan-in/fan-out pass above and run a small
SCC/DFS over it to enumerate cycles; to confirm a suspected pair, `graph.find_shortest_chain(a, b)`
and `graph.find_shortest_chain(b, a)` both returning a chain proves a 2-cycle.
Report each cycle as the chain of components.

## `import-linter` — the Dependency Rule as contracts

Express the Dependency Rule as **contracts** and run them (and leave them behind).
Example `importlinter.ini` the reviewer drafts from the findings:

```ini
[importlinter]
root_package = your_top_package

[importlinter:contract:layers]
name = Dependency Rule: details point inward
type = layers
layers =
    your_top_package.web
    your_top_package.adapters
    your_top_package.application
    your_top_package.domain

[importlinter:contract:framework-out-of-core]
name = Framework is a detail
type = forbidden
source_modules = your_top_package.domain
                 your_top_package.application
forbidden_modules = django
                    sqlalchemy
                    flask
```
Run: `lint-imports --config importlinter.ini` (via the reachable runner). Write the
drafted file to `docs/reports/clean-architecture/importlinter.ini`; **offer** it as
a committed CI tripwire — never commit it silently.

## Abstractness (appendix) — and its Python caveat

`A = abstract classes / total classes` per component. In Python this is
**approximate**: `abc.ABC` subclasses and classes with `@abstractmethod` count,
but `typing.Protocol`s and duck-typed seams do not, so `A` (and therefore
`D = |A + I − 1|`) undercount abstraction. Emit the Main-Sequence table only under
`--metrics`, labelled approximate.

## Degrade path (no graph tool)

Read imports directly: build a rough module→imports map by scanning `import` /
`from ... import` statements, identify the core/detail split from folder names and
framework imports, and reason about cycles and stability qualitatively. State the
limitation in the report; the Dependency-Rule and Screaming-Architecture findings
survive without a tool — only exact cycle enumeration and `I`/`A` numbers are
weaker.
