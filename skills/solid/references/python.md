# Python — SOLID idioms & test detection

How the five principles translate into *idiomatic* Python. The wrong way to
apply SOLID here is to transplant Java: factories, `IInterface` naming, and
class hierarchies where a function would do. Python's duck typing means many
inversions cost almost nothing — use the cheap form.

## Per-principle idioms

**SRP** — split at module level first, class level second. A god class often
becomes: a small domain class + a repository + a notifier, wired in a
composition root. Dataclasses (`@dataclass`) for data-shaped things; plain
functions for stateless transforms — not everything deserves a class.

**OCP** — prefer, in order of ceremony:
1. **Dict dispatch**: `HANDLERS: dict[str, Callable[[Order], Decimal]]` —
   adding a variant = adding one entry. Usually the most readable fix for a
   duplicated `if/elif` chain.
2. **`functools.singledispatch`** when dispatching on argument type.
3. **Strategy objects / registry** only when variants carry state or config.
Do not manufacture a class hierarchy for three stateless variants.

**LSP** — base contracts live in docstrings and type hints; overrides must
honor both. Watch return-type narrowing/widening and `None` leaks. An abstract
method should be declared with `@abstractmethod` (fine to also raise
`NotImplementedError` in its body); a *concrete* override raising it is the
violation.

**ISP** — `typing.Protocol` is the tool: small, structural, zero runtime
coupling — implementors don't even import it. Define the protocol next to the
*client* that needs it (the client owns the interface), with only the methods
that client calls. `runtime_checkable` only if you genuinely isinstance-check.

**DIP** — constructor injection with a Protocol-typed parameter, optionally
with a sensible default so call sites stay simple:

```python
class OrderService:
    def __init__(self, repo: OrderRepository, mailer: Mailer | None = None) -> None:
        self._repo = repo
        self._mailer = mailer or SmtpMailer()   # None sentinel, not a mutable default
```

Kill module-level singletons created at import time (`db = SqliteDb()`); move
construction to the composition root (`main()`, app factory, CLI entry). No DI
framework needed — explicit wiring in one place *is* the pattern. Stdlib
imports (`json`, `pathlib`, `datetime`) are not "dependencies to invert".

## Test suite detection

| Signal | Suite / command |
|--------|-----------------|
| `pyproject.toml` with `[tool.pytest.ini_options]`, or `pytest.ini`, `conftest.py`, `tests/` dir | `pytest` (prefer `python -m pytest` to pin the env) |
| `tox.ini` / `noxfile.py` | `tox` / `nox` — but for the inner loop, run the underlying pytest command |
| `unittest`-style `test*.py` without pytest config | `python -m unittest discover` |
| `Makefile` with a `test` target, or CI workflow files | whatever the target runs — trust the project's own definition first |
| uv/poetry project (`uv.lock` / `poetry.lock`) | prefix: `uv run pytest` / `poetry run pytest` |

Record the exact command and run it from the project root. If both a Makefile
target and raw pytest exist, the Makefile is the project's declared truth.

**Light verification mode** (no suite): `python -m compileall <pkg>` or
`py_compile` each touched file, import every touched module
(`python -c "import pkg.mod"`), run `mypy`/`pyright` if configured, smoke-run
the entry point if there is one.
