# Python — clean-code idioms

The standard ([docs/clean-code-standard.md](../../../docs/clean-code-standard.md)) is
the rubric; this file is what its principles look like in Python, and where applying
them literally makes Python worse.

## Naming

- **No Hungarian, no type prefixes.** `user_list` is worse than `users`; the type is in
  the annotation and the annotation does not go stale the way the name does.
- **`_private` is a convention, not a boundary.** A leading underscore says "not part of
  the contract". A finding that a caller reaches into `_thing` is a real coupling
  finding; a finding that the underscore should have been enforcement is not — Python
  has no such enforcement and does not want one.
- **Comprehension variables get full names.** `[task_status for task_status in statuses]`,
  never `[s for s in statuses]`. A comprehension is the densest code in the file and the
  place a one-letter name costs most.
- **Dunder names are reserved.** A method named `__process__` is not "more Pythonic"; it
  is a name in a namespace the language owns.

## Functions

- **Keyword-only arguments for anything a reader cannot decode at the call site.**
  `def render(report, *, inline=False, badges=None)` — a bare `render(report, True, None)`
  makes the reader open the definition, which is a comment the code is forcing them to
  write.
- **Mutable default arguments are a bug, not a smell.** `def f(items=[])` shares one list
  across every call. File it as Critical; it is a defect with a correct fix (`None` +
  assignment inside).
- **Early return over `else:` after `return`.** The `else` adds a level of indentation
  that carries no information.
- **A generator is not automatically cleaner than a list.** If every caller materialises
  the result, returning a list is more honest and one line shorter at each call site.

## Classes

- **`@dataclass` for data, and stop there.** A hand-written `__init__`/`__eq__`/`__repr__`
  triple that a dataclass would generate is three places for a field to be forgotten.
  `frozen=True` where the thing is a value.
- **`@property` for cheap, side-effect-free access only.** A property that hits the
  network or the database is a method wearing a field's clothes, and the reader has no
  way to see the cost at the call site. This is the side-effect-free-query rule with
  Python-specific teeth.
- **Class-level mutable state is shared state.** A `list` or `dict` at class scope is one
  object for every instance — the same defect as the mutable default, one level up.

## Errors

- **Never a bare `except:`.** It catches `KeyboardInterrupt` and `SystemExit`, so the
  process stops responding to Ctrl-C. `except Exception:` is the widest defensible net,
  and even that wants a reason.
- **Do not swallow.** `except Exception: pass` is the single highest-value clean-code
  finding in most Python codebases. If a failure is genuinely ignorable, the code must
  say why in a comment and log at debug.
- **Raise the specific type, and chain.** `raise ParseError(...) from exc` — the original
  traceback is the evidence the next reader needs, and `from` is how it survives.
- **`try` blocks stay narrow.** A `try` wrapped around thirty lines catches the exception
  from the one you were not thinking about.

## Comments

- **A docstring that restates the signature is noise.** `"""Returns the name."""` on
  `def name(self) -> str` earns nothing. Docstrings earn their place on *why*, on
  invariants, and on the non-obvious edge.
- **Type annotations replace most type comments.** If a comment says what a parameter is,
  annotate it and delete the comment.

## Where this bends

- **A "long" function that is one flat sequence of named steps is fine.** Extracting five
  three-line helpers used once each spreads one story across six places.
- **Duplication across a boundary is not DRY-able.** Two similar-looking validators, one
  for an inbound API payload and one for a domain object, change for different reasons.
- **`if TYPE_CHECKING:` imports look like dead code and are not.** They exist to break a
  runtime import cycle.
- **Test files legitimately repeat themselves.** A test that shares a fixture with nine
  others to avoid four lines of setup has traded readability for a DRY score — that is
  `test-quality`'s call, not this lens's.
