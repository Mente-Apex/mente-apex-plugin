# GoF Patterns Reference

All 23 Gang of Four patterns with Python-specific detection signals, quality
indicators, and opportunity triggers. Shared rubric for the `gof` skill's
analyzer and reviewer. The skill's goal is real reader value: every
*opportunity* must argue a concrete benefit at a specific location, and "no
opportunity" (N/A) is a valid, trust-building outcome.

---

## Table of Contents

**Creational** (5): Abstract Factory · Builder · Factory Method · Prototype · Singleton
**Structural** (7): Adapter · Bridge · Composite · Decorator · Facade · Flyweight · Proxy
**Behavioral** (11): Chain of Responsibility · Command · Interpreter · Iterator ·
  Mediator · Memento · Observer · State · Strategy · Template Method · Visitor

---

## CREATIONAL PATTERNS

### Abstract Factory
**Intent**: Creates families of related objects without specifying their concrete classes.
**Detect by**: Abstract base class (often `ABC`) with 2+ `create_*` / `make_*` methods;
  multiple concrete subclasses that implement ALL those methods; client code receives the
  factory as a dependency (not instantiated inline).
**Grade A**: Uses `abc.ABC` + `@abstractmethod`; client is fully decoupled from concrete
  classes; factory injected via constructor or function param.
**Grade C/D issues**: Factory not abstract (just a plain class); products not consistently
  created through it; concrete factory name hard-coded inside client.
**Suggest when**: Two or more parallel product hierarchies exist (e.g., `WinButton` +
  `WinDialog` vs `MacButton` + `MacDialog`) and creation is scattered.
**Don't suggest when**: Only one product family exists in the codebase — a single factory
  function (or even a plain constructor) is enough until a second family actually shows up.
  Building the family abstraction for a family of one is speculative generality.

---

### Builder
**Intent**: Constructs complex objects step by step, separating construction from representation.
**Detect by**: Class with many setter/`with_*`/`set_*` methods that all return `self`
  (fluent interface); a final `build()` / `create()` / `make()` method; optional
  `Director` class that calls the builder in sequence.
**Grade A**: Clear separation of builder interface vs. concrete builders; Director
  encapsulates common construction sequences; `build()` validates required fields.
**Grade C/D issues**: Builder directly inherits the product; setters modify global state;
  no validation before `build()`; used when a simple constructor would suffice.
**Suggest when**: A class has 5+ constructor parameters, especially optional/defaulted
  ones, or when the same object must be built in multiple configurations.
**Don't suggest when**: The object has ≤4 params, or is a simple dataclass — a keyword
  constructor (or `dataclasses.replace` for variants) reads better than a fluent builder
  with a `Director` on top.

---

### Factory Method
**Intent**: Defines an interface for creating an object but lets subclasses decide which class to instantiate.
**Detect by**: Base class with a method (`create_*`, `make_*`, or simply named after the
  product) that returns an object; subclasses override ONLY that method to change the
  product type; the method is called from base-class logic that uses the result.
**Grade A**: Factory method is clearly abstract or has a documented extension point;
  subclasses override without touching base logic; product interface used throughout.
**Grade C/D issues**: Factory method also contains business logic; product returned as
  a concrete type (not abstracted); subclass doesn't actually change the product.
**Suggest when**: A class creates objects internally and you anticipate needing different
  variants — the `if/elif` block that picks a class to instantiate is a red flag.
**Don't suggest when**: Only one concrete product exists today, or the `if/elif` is a
  single site unlikely to grow — a plain constructor call or one conditional is more
  readable than a subclass hierarchy built for a variant that may never arrive.

---

### Prototype
**Intent**: Creates new objects by copying (cloning) an existing instance.
**Detect by**: `copy.copy()` / `copy.deepcopy()` calls; custom `clone()` / `copy()` /
  `__copy__()` / `__deepcopy__()` methods; a registry dict mapping names to prototype
  instances with a `get(name)` that returns a clone.
**Grade A**: Uses Python's `copy` module correctly; deep vs. shallow copy is a
  deliberate choice; prototype registry prevents redundant instantiation.
**Grade C/D issues**: Manual attribute-by-attribute copy (misses new fields); shallow
  copy used where mutable nested objects demand deep copy; no registry (defeats the
  point of caching expensive-to-create objects).
**Suggest when**: Object initialization is expensive (DB load, file parse, complex
  calculation) and multiple similar instances are needed; or when runtime cloning of
  configured objects is required.
**Don't suggest when**: Construction is cheap (a plain dataclass, no I/O, no heavy
  computation) — `copy.deepcopy()` on an ad-hoc basis, or just calling the constructor
  again, is simpler than standing up a clone registry.

---

### Singleton
**Intent**: Ensures a class has exactly one instance and provides a global access point.
**Detect by**: Class-level `_instance` attribute; overridden `__new__`; `@classmethod`
  named `get_instance()` / `instance()`; module-level single object used everywhere.
**Grade A**: Thread-safe (uses a lock); instantiation is lazy; Python module-level
  singleton preferred over class-based when appropriate; no global mutable state abuse.
**Grade C/D issues**: Not thread-safe (`if cls._instance is None` race condition without
  lock); used for objects that don't need global uniqueness; makes testing hard
  (no reset mechanism); subclassing breaks the guarantee.
**Suggest when**: Truly global shared resource — config loader, logger, connection pool —
  where multiple instances would cause resource contention or inconsistency.
**Don't suggest when**: Almost always — prefer a module-level object or dependency
  injection; a Singleton usually *adds* a DIP/testability problem rather than solving one.
  Only note it for a genuinely global resource, and cross-check the overlap map's ⚠
  tension before recommending it.

---

## STRUCTURAL PATTERNS

### Adapter
**Intent**: Converts one interface into another that clients expect.
**Detect by**: Class that wraps another object (`self._adaptee = ...`) and exposes a
  different API; method delegation with parameter transformation; often named `*Adapter`
  or `*Wrapper`; bridges two incompatible interfaces (e.g., legacy API + new system).
**Grade A**: Thin wrapper — only translates interface, no added logic; adaptee injected
  (not hardcoded); follows target interface contract exactly.
**Grade C/D issues**: Adapter also adds business logic (mixing concerns); adaptee class
  hardcoded inside adapter; adapter inherits from adaptee instead of wrapping it
  (use composition over inheritance).
**Suggest when**: Third-party library or legacy code has an incompatible interface that
  can't be changed; you see direct usage of that API scattered across many call sites.
**Don't suggest when**: You own both interfaces and can simply change one — an adapter
  only earns its keep against code you can't (or shouldn't) modify. If there's a single
  call site, just convert the value inline instead of naming a wrapper class.

---

### Bridge
**Intent**: Decouples an abstraction from its implementation so both can vary independently.
**Detect by**: Two class hierarchies that reference each other via composition (not
  inheritance); abstraction class holds a reference to an `implementor`; methods on
  the abstraction delegate to the implementor; often used for platform/rendering variants.
**Grade A**: Both hierarchies are independent and composable; abstraction never
  references concrete implementors; implementor injected at construction.
**Grade C/D issues**: Abstraction and implementation still coupled via subclassing;
  only one dimension actually varies; confused with Adapter (Bridge is proactive
  design, Adapter is retrofit).
**Suggest when**: A class hierarchy risks combinatorial explosion (e.g., `RedCircle`,
  `BlueCircle`, `RedSquare`, `BlueSquare` → split into Shape + Color hierarchies).
**Don't suggest when**: Only one dimension actually varies, or the combinations total
  2–3 — a single subclass hierarchy or an `if/else` on the one axis is simpler than
  standing up two coordinated hierarchies for variation that isn't there yet.

---

### Composite
**Intent**: Composes objects into tree structures to represent part-whole hierarchies.
**Detect by**: A component interface/ABC with `add()`, `remove()`, `children` or similar;
  leaf classes and composite classes both implement the same interface; recursive
  operations (e.g., `render()`, `calculate()`) that call the same method on children.
**Grade A**: Component interface is clean; `Composite` treats `Leaf` uniformly; recursive
  calls are safe (handles empty children); client never distinguishes leaf from composite.
**Grade C/D issues**: `isinstance` checks to differentiate leaf from composite (breaks
  uniformity); `children` exposed on both leaf and composite (violates interface segregation);
  no shared interface — just ad-hoc recursion.
**Suggest when**: A tree structure is being built manually (nested dicts/lists) or
  recursive traversal code has many type checks.
**Don't suggest when**: The structure is shallow and fixed-depth (e.g., always exactly
  one level of children, never nested further) — plain list iteration is clearer than a
  recursive component tree built for depth that will never occur.

---

### Decorator
**Intent**: Attaches additional responsibilities to an object dynamically, as a flexible alternative to subclassing.
**Detect by**: Class wrapping another of the **same type/interface** (`self._component`);
  adds behavior before/after delegating to wrapped object; Python `@functools.wraps` or
  class decorators that preserve interface; stacked wrappers.
**Grade A**: Decorator and component share a common interface; transparent to the client;
  stacking works correctly; Python function decorators used where appropriate.
**Grade C/D issues**: Decorator doesn't implement full component interface (breaks
  substitutability); state leaks between stacked decorators; confused with Proxy
  (Decorator adds behavior; Proxy controls access).
**Suggest when**: Cross-cutting concerns (logging, caching, auth, validation) are being
  copy-pasted into multiple classes instead of being applied uniformly.
**Don't suggest when**: There's a single one-off wrapping used in exactly one place —
  inline the behavior or use a plain Python function decorator. Reach for a class-based,
  stackable Decorator only once 2+ cross-cutting concerns actually need to compose.

---

### Facade
**Intent**: Provides a simplified interface to a complex subsystem.
**Detect by**: Class that delegates to 3+ other classes/modules with no business logic of
  its own; often a single entry point used by most client code; named `*Service`,
  `*Manager`, `*API` (when it purely delegates); imports from many subsystems.
**Grade A**: Subsystem classes remain usable directly; facade doesn't add restrictions;
  facade is thin (delegates, doesn't transform logic); dependencies injected.
**Grade C/D issues**: Facade grows into a "god class" that owns business logic; subsystem
  tightly coupled to facade; facade forces all access through itself (removes flexibility).
**Suggest when**: Client code directly orchestrates 3+ subsystem classes in the same
  sequence repeatedly; or a complex library is used directly across many call sites.
**Don't suggest when**: The subsystem is already one or two classes, or the "facade"
  would just be a pass-through with no orchestration to simplify — that's an unnecessary
  layer of indirection, not a simplification.

---

### Flyweight
**Intent**: Shares common state among many fine-grained objects to reduce memory usage.
**Detect by**: Factory/registry that caches and reuses instances (dict keyed by intrinsic
  state); objects split into intrinsic (shared) + extrinsic (per-context) state;
  large numbers of similar objects.
**Grade A**: Clear separation of intrinsic vs. extrinsic state; factory enforces sharing;
  extrinsic state passed to methods rather than stored on the object.
**Grade C/D issues**: Intrinsic and extrinsic state mixed on the object (mutability
  bugs); cache never evicted (memory leak); used in a context with few objects (premature
  optimization).
**Suggest when**: Profiling shows many instances of the same logical object (e.g., text
  characters, game tiles, UI style tokens) consuming significant memory.
**Don't suggest when**: There's no profiling evidence of memory pressure — sharing and
  caching add indirection to solve a problem that may not exist. A handful of duplicate
  objects is not a Flyweight case; measure before optimizing.

---

### Proxy
**Intent**: Provides a surrogate to control access to another object.
**Detect by**: Class that wraps another of the **same interface** and adds access control,
  lazy loading, caching, or logging; `__getattr__` delegation; lazy-initialized `_real_subject`.
**Grade A**: Proxy and real subject share interface; proxy is transparent to client;
  access control / lazy loading logic is isolated and not mixed with subject logic.
**Grade C/D issues**: Proxy breaks the subject's interface; proxy adds business logic
  (becomes a Decorator); client must know it's using a proxy (defeats purpose).
**Suggest when**: An expensive resource should be lazily loaded; access to an object
  needs to be gated or logged; remote object needs a local stand-in.
**Don't suggest when**: The "access control" is a single boolean check or an early
  return — an inline guard clause at the call site is clearer than introducing a wrapper
  class that mirrors the subject's whole interface for one gate.

---

## BEHAVIORAL PATTERNS

### Chain of Responsibility
**Intent**: Passes a request along a chain of handlers until one handles it.
**Detect by**: Handler base class with `set_next()` / `successor` / `next_handler`;
  `handle()` method that either processes or passes to `self._next.handle()`; linked
  list or list of handlers iterated at runtime.
**Grade A**: Handlers independent of each other; chain assembled externally (not
  hardcoded inside handlers); termination condition clear; request can go unhandled
  gracefully.
**Grade C/D issues**: Handlers are tightly coupled (know each other's types); chain
  hardcoded inside a handler; infinite loop risk (no termination); mimics if/elif (use
  a dispatch table instead).
**Suggest when**: A request must pass through multiple validation/processing steps
  and the order or set of handlers may change at runtime.
**Don't suggest when**: There are only 2–3 fixed checks that never reorder or change at
  runtime — a plain function calling them in sequence (or a single `if` with early
  returns) beats a linked list of handler objects.

---

### Command
**Intent**: Encapsulates a request as an object, allowing parameterization, queuing, and undo.
**Detect by**: Classes with a single `execute()` method; a list/queue of command objects;
  `undo()` / `unexecute()` methods; `Invoker` class that calls `command.execute()`.
**Grade A**: Commands are self-contained (carry all needed data); `undo()` is symmetric;
  invoker doesn't know command internals; commands are serializable if queuing needed.
**Grade C/D issues**: Command has side effects but no `undo()`; invoker directly calls
  receiver instead of going through command; commands mutate global state.
**Suggest when**: Actions need undo/redo; operations need to be queued, scheduled, or
  logged; UI actions should be decoupled from business logic.
**Don't suggest when**: There's no actual need for undo, queuing, or deferred/logged
  execution — wrapping every action in a command object "just in case" is ceremony;
  a direct method call is clearer until one of those needs materializes.

---

### Interpreter
**Intent**: Defines a grammar and an interpreter for a language.
**Detect by**: AST node classes (each representing a grammar rule); `interpret(context)`
  method on each node; recursive tree evaluation; often paired with a parser.
**Grade A**: Grammar is clearly modelled by the class hierarchy; context passed cleanly;
  recursive interpretation is side-effect-free.
**Grade C/D issues**: Grammar logic mixed into parser; no clear AST — just string
  manipulation; used for a language complex enough to need a real parser generator.
**Suggest when**: A simple domain-specific language or expression evaluator is needed
  and the grammar is small (< ~10 rules).
**Don't suggest when**: There's only one expression shape (a plain function suffices),
  or the grammar is large/growing — reach for an existing parser (`ast`, a small parser
  library) rather than hand-rolling a node class per rule.

---

### Iterator
**Intent**: Provides sequential access to a collection without exposing its structure.
**Detect by**: `__iter__` + `__next__` implementation; `yield` / generator functions;
  custom iterator class separate from the collection.
**Grade A**: Follows Python iterator protocol properly; `__iter__` returns `self` on
  iterators; generators preferred over manual `__next__` for simple cases; stateless
  where possible.
**Grade C/D issues**: Iterator maintains shared state with collection (mutation hazard);
  `__iter__` returns the collection itself (can't have two simultaneous iterators);
  manual index tracking instead of using `yield`.
**Suggest when**: A custom data structure (tree, graph, circular buffer) needs to
  support `for x in ...` — implement `__iter__`/`__next__` or a generator.
**Don't suggest when**: A plain generator function or the container's built-in iteration
  (list/dict/set) already does the job — naming a bespoke `Iterator` class that
  duplicates what `yield` gives you for free is pure ceremony.

---

### Mediator
**Intent**: Defines an object that encapsulates how a set of objects interact, reducing coupling.
**Detect by**: Central class that other objects hold a reference to and call to
  communicate; objects don't reference each other directly; `notify()` / `send()` on
  mediator; event bus / message broker implementations.
**Grade A**: Colleagues only know the mediator interface; mediator coordinates without
  owning business logic; loose coupling enables independent testing.
**Grade C/D issues**: Mediator becomes a god class (owns too much logic); colleagues
  still reference each other directly; circular dependency between mediator and colleagues.
**Suggest when**: Many objects communicate in complex, tangled ways — many-to-many
  dependencies between components that should be independent.
**Don't suggest when**: Only 2–3 objects talk to each other and the interaction is
  already clear direct calls — inserting a mediator layer is overhead until the
  many-to-many tangle actually exists.

---

### Memento
**Intent**: Captures and externalizes an object's internal state for later restoration, without violating encapsulation.
**Detect by**: Inner class or standalone class that stores a snapshot of another object's
  state; `save_state()` / `create_memento()` and `restore_state()` / `restore()` methods;
  history stack of memento objects.
**Grade A**: Memento only accessible to originator (encapsulation preserved); caretaker
  stores mementos without inspecting them; state snapshots are independent (not references).
**Grade C/D issues**: Memento exposes internal state publicly; deep copy not used where
  needed (snapshot contains live references); state stored on a "history" list directly
  on the originator (blurs caretaker responsibility).
**Suggest when**: Undo/redo is needed for an object with complex state; user actions
  should be reversible; state must be checkpointed.
**Don't suggest when**: The state is a small immutable value — `dataclasses.replace()`
  or simply keeping a list of past values already gives you undo without a dedicated
  Memento class and caretaker.

---

### Observer
**Intent**: Defines a one-to-many dependency so all dependents are notified automatically when the subject changes.
**Detect by**: List of listeners/subscribers/callbacks (`_observers`, `_listeners`,
  `_callbacks`); `subscribe()` / `attach()` / `add_listener()` methods; `notify()` /
  `emit()` / `dispatch()` that iterates the list; Python `signal` libraries or event hooks.
**Grade A**: Subject depends only on observer interface (not concrete classes); observers
  can be added/removed at runtime; notification doesn't rely on observer order; thread
  safety handled if multi-threaded.
**Grade C/D issues**: Subject directly calls concrete observer methods (tight coupling);
  no way to unsubscribe (memory leak); observers not notified of what changed (pull model
  done badly); circular notification chains.
**Suggest when**: One object's state change should trigger reactions in an unknown number
  of other objects; event hooks, callbacks, or notification lists appear scattered.
**Don't suggest when**: There's a single, static listener — a direct call is clearer than
  a subscription list built for a fan-out that never happens.

---

### State
**Intent**: Allows an object to alter its behaviour when its internal state changes, appearing to change its class.
**Detect by**: State classes (often named `*State`) that implement a common interface;
  context object delegates to current state; `transition()` calls change `self._state`.
**Grade A**: State transitions are explicit and managed by state classes or context
  (not scattered `if/elif`); context API is stable regardless of state; states are
  independent and testable.
**Grade C/D issues**: State stored as a string/enum with `if/elif` chains (use this
  pattern to eliminate those); state classes access context's private state directly;
  transition logic duplicated across states.
**Suggest when**: A class has a large `if/elif` block based on a "state" variable, and
  behaviour differs substantially per state.
**Don't suggest when**: There are only 2–3 states with simple, stable transitions — a
  single `if/elif` or an enum check is more readable than a class per state, and the
  extra files cost more than the conditional they replace.

---

### Strategy
**Intent**: Defines a family of algorithms, encapsulates each one, and makes them interchangeable.
**Detect by**: Class that accepts a callable or object with a specific method (`execute()`,
  `sort()`, `compress()` etc.) at construction or via a setter; algorithm swapped at
  runtime; often named `*Strategy`; Python: passing functions as first-class args.
**Grade A**: Strategy interface is minimal and focused; context is fully decoupled from
  concrete strategies; strategies are stateless or clearly documented when stateful;
  Python lambdas/functions used for simple strategies.
**Grade C/D issues**: Strategy tied to context internals (knows too much); only one
  strategy ever used (not really a strategy); strategy injected but never swapped.
**Suggest when**: A method has a large conditional block (`if algo == "x"`) choosing
  between multiple algorithms; algorithms need to be configurable or swappable at runtime.
**Don't suggest when**: There is a single algorithm, or only 2–3 stable branches a dict
  dispatch handles more readably; a strategy-class explosion for three cases is worse.

---

### Template Method
**Intent**: Defines the skeleton of an algorithm in a base class, deferring some steps to subclasses.
**Detect by**: Base class method that calls several `_step_*()` / `do_*()` hook methods
  in a fixed order; subclasses override only the hooks; base class orchestrates the
  overall flow.
**Grade A**: Template method is clearly documented as the algorithm entry point; hook
  methods have sensible defaults where appropriate; subclasses override only what varies.
**Grade C/D issues**: Subclasses override the template method itself (defeats purpose);
  too many hooks (subclasses must implement everything, better use Strategy); base class
  calls abstract methods that have no default and aren't documented.
**Suggest when**: Multiple classes share the same algorithm skeleton but differ in
  specific steps — copy-pasted methods with minor variations are a strong signal.
**Don't suggest when**: There's only one concrete subclass, or subclasses would end up
  overriding the whole method anyway — passing the varying step in as a function
  (composition) is simpler than an inheritance hierarchy built for variation that isn't
  there yet.

---

### Visitor
**Intent**: Lets you add operations to objects without modifying them, by separating the algorithm from the object structure.
**Detect by**: `accept(visitor)` method on element classes; visitor class with
  `visit_<ElementType>()` methods; double-dispatch pattern.
**Grade A**: Visitor interface covers all element types; elements don't contain the
  visiting logic; adding a new visitor doesn't change element classes.
**Grade C/D issues**: `accept()` does work beyond dispatch (mixes concerns); visitor
  uses `isinstance` instead of double dispatch; adding a new element type requires
  updating all visitors (acceptable tradeoff, but note it).
**Suggest when**: Many unrelated operations need to run across a stable object hierarchy
  (AST transformations, document rendering, serialization formats); you don't want to
  pollute element classes with every new operation.
**Don't suggest when**: The hierarchy changes often (adding an element type forces every
  visitor to change) or a simple method on each element already suffices — Visitor
  trades one kind of change (new operation) for another (new type), and that trade is
  only worth it when operations grow faster than element types.

---

## Grade rubric (detected patterns)
Always use the full label, not just the letter.
- **A — Clean implementation** — idiomatic Python; follows GoF intent; no obvious flaws
- **B — Mostly correct** — minor deviations (missing abstraction, slight coupling)
- **C — Structural issues** — recognizable but partially broken or awkward
- **D — Significantly misimplemented** — intended as the pattern but mostly wrong
- **F — Fundamentally incorrect** — wrong in a way that could cause harm
A mediocre singleton is a C, not a B. Grade honestly.

## Tier rubric (actionable recommendations: opportunities + low-grade patterns)
Tier by reader impact × blast radius, matching the `solid` lens so the shared
apply phase is identical.
- **Critical** — a missing/forced pattern actively blocks comprehension or safe
  change today (a duplicated hand-rolled dispatch in 3+ places; a god facade).
- **Major** — clear, recurring friction, contained blast radius (a two-site
  dispatch that wants Strategy; a D-grade pattern in one subsystem).
- **Minor** — emerging or cosmetic-adjacent; cheap, low urgency.
When in doubt, tier down.

## Risk rubric (Low / Medium / High)
Risk = chance the *change* breaks something, independent of tier. Gates the apply
phase: High-risk recs get individual human confirmation.
- **Low** — internal, mechanical, well covered (introduce a Protocol, inject a
  strategy with a default).
- **Medium** — several call sites or partially tested code.
- **High** — public API signatures, cross-module moves, persistence-adjacent, or
  untested code. Rated up when in doubt.
