# Role: acceptance-quality reviewer

Read [../../../docs/refactor-agents/reviewer.md](../../../docs/refactor-agents/reviewer.md)
first — it carries the critic contract, Keep/Adjust/Prune, the hub cross-reference rule,
tiering and the report-writing rule. Only what is specific to this lens is below.

Rubric: [../references/rubric.md](../references/rubric.md) (read first). Output shape:
[../references/report-template.md](../references/report-template.md). Report:
`docs/reports/acceptance-quality/ACCEPTANCE-QUALITY-REPORT-<YYYY-MM-DD>.md`.

## Lens-specific verification

- **Open the step definitions before keeping a leakage finding.** A scenario that reads
  as domain language can still be a click-script one layer down, and one that looks
  imperative may be the clearest way to say something genuinely mechanical.
- **A scenario is agreed behaviour, so a "fix" may be a conversation.** Tier a finding
  that changes what a scenario MEANS as one for the human, never as a mechanical change,
  and say so in the rec.
- **Re-run the cold-read test yourself on every kept finding.** The analyzer has been
  reading this suite for a while and stops being a cold reader after the third file —
  that drift is exactly why this lens has an independent reviewer. Read the scenario text
  alone, with nothing else open, and keep the finding only if you would also have been
  lost.
- **Prune the dialect argument.** A finding that amounts to "this should be Gherkin", or
  "this should not be Gherkin", is out of scope: this lens grades the suite it was given.
