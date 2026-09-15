# Gherkin — the deepest-supported dialect

The rubric ([rubric.md](rubric.md)) is what to look for; this file is what it looks like
in Gherkin (Cucumber, SpecFlow, Behave, pytest-bdd, Reqnroll). Another dialect is another
file in this directory — that is the seam, and it is the reason this lens detects rather
than assumes.

## Reading the feature file

- **`Feature:` should name a capability**, not a screen or a component.
- **`Scenario:` should read as a sentence a stakeholder would say out loud.** If the
  title only makes sense to someone who has read the step definitions, that is the
  spec-as-spec smell.
- **`Scenario Outline` + `Examples` is the right tool for the same behaviour with
  different data** — and the wrong one for different behaviours forced into one shape.
  A column that changes the `Then` is two scenarios.
- **`Background` runs before every scenario in the file.** Setup for some of them belongs
  in those scenarios, or in a separate file.

## Tags

- `@wip`, `@skip`, `@ignore` with no reason are obsolete pins.
- Tags used for *selection* (`@smoke`, `@slow`) are infrastructure and fine.
- A tag used to encode behaviour (`@admin` changing what the steps do) hides a
  precondition that belongs in a `Given`.

## Step definitions

- **A step definition with an `if` means the step means two things.** Split it.
- **Regex or Cucumber-expression steps that overlap** are the near-duplicate smell in its
  most damaging form: which definition runs depends on registration order.
- **Steps that reach into the database or the DOM to assert** are the leakage smell one
  layer down — the scenario reads clean and the step is a click-script.
- **World / context object as a dumping ground** — state passed between steps through a
  shared bag is how scenarios become order-dependent.

## The runner-specific bits worth checking

- **Cucumber-JVM / SpecFlow / Reqnroll:** step definitions in a class with constructor
  injection are testable; static state in a step class is shared across scenarios by
  construction.
- **pytest-bdd:** step functions are fixtures, so an `autouse` fixture in a `conftest.py`
  can silently change what a scenario means.
- **Behave:** `context` is genuinely global for the run; anything stored there in a
  `Given` outlives the scenario unless it is cleaned.

## Where this bends

- **An API feature file legitimately names HTTP verbs and status codes** — those ARE the
  agreed behaviour when the stakeholder is another service.
- **A long `Examples` table is not duplication.** It is one scenario with data.
- **Gherkin's ceremony is not itself a finding.** If the team chose it, grade the suite
  they wrote; "this should not be Gherkin" is out of scope, and so is the reverse.
