# Python — GoF idioms & test detection

How the 23 patterns translate into *idiomatic* Python. The wrong way to apply
GoF here is to transplant Java: `IFactory` interfaces, abstract-everything
class hierarchies, and ceremony where a function, a dict, or a generator
would do. Python's first-class functions, duck typing, and stdlib (`copy`,
`functools`, `abc`) make several patterns nearly free — use the cheap form,
and grade an over-engineered implementation down just as readily as a
broken one.

## Per-pattern idioms

### Creational

**Singleton** — a module-level instance (`_registry = Registry()` at import
time, imported by callers) is almost always the right answer; it's
thread-safe for free and doesn't need a class at all. A `__new__` override
with a `_instance` class attribute is the textbook form but needs an
explicit `threading.Lock()` around the check to be safe under concurrent
first access — grade C/D if that guard is missing. A metaclass-based
Singleton is rarely worth the indirection unless several classes need the
same behavior. Note the DIP tension recorded in the `solid-gof-overlap`
map: SOLID prefers constructor injection over any singleton, so weigh both
lenses before suggesting one.

**Factory Method** — a `@classmethod` alternate constructor
(`Shape.from_config(cfg)`) is idiomatic Python where the GoF write-up
reaches for a subclass hierarchy. Reserve the subclass-per-product form for
when subclasses genuinely need different *behavior* around creation, not
just a different return type.

**Abstract Factory** — `abc.ABC` + `@abstractmethod` for the factory
interface, with each concrete factory returning a family of related
products. This is the one creational pattern that earns its class
hierarchy: family-of-products coupling is exactly what `abc` is for. Grade
down a factory that isn't actually abstract (a plain class with no
enforced contract) or where the client still imports concrete product
classes directly.

**Builder** — a fluent chain of `with_*` methods returning `self`, or for
immutable data, `dataclasses.replace(instance, **changes)` — skip the
`Director` class entirely unless the same multi-step sequence is reused
across several call sites. A `@dataclass` with keyword defaults already
covers most "many optional constructor params" cases without any Builder.

**Prototype** — `copy.deepcopy()` / `copy.copy()` directly, or custom
`__copy__`/`__deepcopy__` when the default field-by-field copy is wrong for
some attribute (e.g. a shared connection that must NOT be cloned). A
hand-rolled attribute-by-attribute copy method is a maintenance trap: new
fields silently aren't cloned — grade C/D and recommend `copy.deepcopy`.

### Structural

**Adapter** — a thin wrapper class translating one call signature to
another, or in many cases nothing at all: Python's duck typing means two
objects with the same method names are already interchangeable without an
adapter class. Only recommend Adapter when the signatures genuinely
differ.

**Bridge** — composition over inheritance: the abstraction holds a
reference to an implementor object rather than subclassing it, avoiding
the `M abstractions × N implementations` subclass explosion.

**Composite** — a common base (`abc.ABC` or a `Protocol`) shared by leaf and
composite nodes, with the composite delegating to children in a loop or
recursive call. `isinstance` checks scattered through traversal code are
the signal this pattern is missing.

**Decorator** — `functools.wraps` on function decorators to preserve
`__name__`/`__doc__`; class-based decorators (`__call__` wrapping another
callable) when the decorator itself needs configuration or state. Prefer a
plain decorator function until state is actually needed — don't reach for a
class by default.

**Facade** — a module-level function or a small class exposing 2-3 methods
that internally sequence several subsystem calls. No special Python
mechanism — the win is purely in the client no longer importing every
subsystem class directly.

**Flyweight** — `functools.lru_cache` (or a manual dict keyed by the
shared-state fields) to intern/reuse instances instead of constructing
duplicates. Only worth suggesting when profiling or object counts show real
memory pressure — don't add a cache for its own sake.

**Proxy** — `__getattr__` delegating to a wrapped object for
lazy-loading, access control, or logging, so the proxy's public surface
stays identical to the real subject without hand-copying every method.

### Behavioral

**Chain of Responsibility** — a list of handler callables tried in order,
each returning a sentinel (or raising) to signal "not handled, try the
next" — usually simpler than a linked list of handler objects with a
`set_next()` method.

**Command** — a `Callable` (function, `functools.partial`, or a small
class implementing `__call__`) queued and invoked later; add an `undo()`
method only when undo is actually needed, not speculatively.

**Interpreter** — recursive-descent over a small `@dataclass`-based AST is
the idiomatic shape; reach for a parser-generator library instead of a
hand-rolled Interpreter class hierarchy once the grammar grows past a
handful of rules.

**Iterator** — `__iter__` returning a generator (or the class itself being
a generator function) beats a hand-written `Iterator` class with manual
`__next__`/`StopIteration` bookkeeping in almost every case. Only write an
explicit iterator class when the iteration needs to be paused, inspected,
or restarted mid-stream in ways a generator can't express cleanly.

**Mediator** — a dedicated coordinator object that colleagues call into
instead of calling each other directly, collapsing many-to-many references
into many-to-one. Watch for the mediator itself becoming a god object —
that's a SRP handoff, not a reason to avoid Mediator.

**Memento** — an immutable snapshot, often just `copy.deepcopy(self.__dict__)`
or a `@dataclass(frozen=True)` capturing the fields that matter, returned
from a `save()` method and restored via `restore(snapshot)`. No need for a
formal `Memento` class when a `namedtuple` or frozen dataclass says the
same thing.

**Observer** — a list of `Callable` subscribers (`self._listeners:
list[Callable[[Event], None]] = []`) with `subscribe`/`unsubscribe`/`notify`
methods; the "observer interface" is just a function signature, not a
class hierarchy, unless observers carry meaningful state of their own.

**State** — dict dispatch keyed by an `Enum` (`_TRANSITIONS: dict[State,
Callable]`) is often enough; promote to full State-object subclasses only
when each state needs to own several methods' worth of distinct behavior,
not just a different return value.

**Strategy** — a `Callable` parameter (`Callable[[Order], Decimal]`) passed
in or looked up from a dict, exactly like the SOLID OCP idiom — Strategy
and OCP's "dict dispatch" recommendation are the same fix seen from two
lenses. Only build a class-based strategy hierarchy when strategies carry
their own configuration/state beyond a single function's closure.

**Template Method** — an `abc.ABC` with a concrete "skeleton" method calling
several `@abstractmethod` hook methods, or, more idiomatically in Python, a
single function that takes the varying steps as injected callables —
avoids forcing a subclass just to override one step.

**Visitor** — `functools.singledispatch` (or `singledispatchmethod` for
methods) dispatching on the element's type, instead of a hand-rolled
`isinstance` chain or a formal `accept()`/`visit()` double-dispatch
hierarchy. Reach for the classic double-dispatch form only when the
element hierarchy is genuinely closed and stable and operations must live
outside the elements.

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
