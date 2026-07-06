# Python Adapter — pytest

Stack-specific mechanics for the core TDD cycle. The cycle itself lives in SKILL.md;
this file covers how to execute it in a Python project.

## Discovering conventions

Check, in order:

1. **Runner config** — `pyproject.toml` (`[tool.pytest.ini_options]`), `pytest.ini`,
   `setup.cfg`. Note `testpaths`, custom markers, and addopts before running anything.
2. **Layout** — most projects use `tests/` mirroring the package; some co-locate
   `test_*.py` next to modules. Follow whichever exists.
3. **Shared fixtures** — read `conftest.py` at each level before writing setup code;
   the fixture you need may already exist.
4. **How tests are run** — `uv run pytest`, `poetry run pytest`, `tox`, or bare
   `pytest`. Match the project's lockfile/tooling; running the wrong environment
   produces misleading failures.

Greenfield defaults: `tests/` directory, `test_` prefix, `conftest.py` for shared
fixtures, plain `assert` statements.

During the cycle, run the single new test first (`pytest tests/test_x.py::test_name -x -q`),
then the full suite.

## Fixtures are the injection seam

Fixtures do double duty: test setup, and the place where dependency injection pays off.
A class that takes its collaborators as constructor parameters gets a one-line fixture;
a class that builds its own database client needs patching — which is the design smell
the REFACTOR checklist tells you to fix.

```python
@pytest.fixture
def user_repository():
    return InMemoryUserRepository()

def test_can_add_and_retrieve_user(user_repository):
    user = User(name="Alice", email="alice@example.com")
    user_repository.add(user)
    assert user_repository.get_by_email("alice@example.com") == user
```

## Expected exceptions

```python
def test_raises_on_duplicate_email(user_repository):
    user_repository.add(User(name="Alice", email="alice@example.com"))
    with pytest.raises(DuplicateEmailError):
        user_repository.add(User(name="Bob", email="alice@example.com"))
```

Assert on the exception type, not string matching against the message, unless the
message itself is the contract.

## Parametrize for variations

```python
@pytest.mark.parametrize("invalid_email", ["", "noatsign", "@nodomain", "spaces in@email.com"])
def test_rejects_invalid_email(invalid_email):
    with pytest.raises(ValidationError):
        User(name="Test", email=invalid_email)
```

Use parametrize when testing the *same behavior* with different inputs. Distinct
behaviors get distinct tests — cramming them into one parametrized test hides which
specification broke.

In the one-test-at-a-time cycle, a parametrized test counts as one test: introduce it
with one case, make it pass, then add cases one at a time — each new case is its own
RED step if it fails.

## Useful built-ins before reaching for anything else

- `tmp_path` — per-test temporary directory; never write test files into the repo.
- `monkeypatch` — environment variables and attribute patching at *infrastructure
  boundaries only*. If you're monkeypatching your own domain code, the dependency
  should be injected instead (see `ddd_testing.md` — this rule is absolute for domain
  layers).
- `capsys` — captured stdout/stderr for CLI-facing code.
- Markers (`@pytest.mark.slow`, custom markers from the project config) — respect
  existing ones; suggest one when the suite grows a slow integration section.
