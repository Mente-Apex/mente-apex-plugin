# GoF HTML preview

The renderer is shared — see [../../../docs/html-previews.md](../../../docs/html-previews.md)
for the command, the self-containment rules and why it is a script rather than a
styling spec (issue #130). This file keeps only what is this lens's own.

## Vocabulary

`gof` badges **pattern grades A–F**, not Critical/Major/Minor tiers, so it
renders with `--badges grade`:

    sh "$CLAUDE_PLUGIN_ROOT/bin/mente-python" "$CLAUDE_PLUGIN_ROOT/scripts/report_html.py" \
        docs/reports/gof/GOF-REPORT-<YYYY-MM-DD>.md --badges grade

| Grade | Colour |
|---|---|
| A — Clean implementation | green `#22c55e` |
| B | blue `#3b82f6` |
| C — Structural issues | amber `#f59e0b` |
| D | orange `#f97316` |
| F | red `#dc2626` |

The grade scale is a real distinction this lens makes about an *existing*
implementation, which is why it was not flattened into the tier scale when the
renderer was shared: a `C` Singleton is not a "Major finding", it is a working
pattern with a stated gap.

## Under the umbrella

`/code-quality` instructs this lens's reviewer to **skip the HTML preview** — the
one consolidated report is the product there, and six per-lens previews are six
files nobody opens.
