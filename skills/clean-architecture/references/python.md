# clean-architecture in Python — tooling & metrics

The headline checks want the real import graph. Use a tool when one is reachable;
**degrade gracefully** when not. Other languages: `dependency-cruiser` / `madge`
(JS/TS) do the equivalent; else fall back to reading imports.

## Detect a graph tool (no hard install)

Try, in order, whatever the environment offers — a project-local install
(`python -c "import grimp"`), then a runner (`uvx import-linter`, `pipx run
import-linter`). Record which path succeeded. If **none** is reachable, switch to
the **degrade path** below and state "agent-driven (no graph tool)" in the report.

## `grimp` — the import graph, cycles, and Instability

Compute Instability (the SDP metric) using fan-in and fan-out:

```python
import grimp

graph = grimp.build_graph("your_top_package")          # the package under audit
components = graph.find_children("your_top_package")     # the sub-packages = components

for component in sorted(components):
    fan_out = len(graph.find_modules_directly_imported_by(component))  # efferent
    fan_in = len(graph.find_modules_that_directly_import(component))    # afferent
    denominator = fan_in + fan_out
    instability = fan_out / denominator if denominator else 0.0         # SDP metric
    print(component, round(instability, 2))
```
Cycles (ADP): `grimp` exposes them directly —
`graph.find_illegal_dependencies_for_layers(...)` for layered contracts, and cycle
detection over `find_children`. Report each cycle as the chain of components.

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
