# HTML previews — one renderer, every lens

Any lens report, and the umbrella's consolidated report, can be rendered as a
self-contained HTML preview beside its Markdown. `gof` used to be the only lens
with this, as a 114-line per-lens styling spec an agent re-executed with a Write
call on every run (issue #130). It is now a script, once:

    sh "$CLAUDE_PLUGIN_ROOT/bin/mente-python" "$CLAUDE_PLUGIN_ROOT/scripts/report_html.py" \
        docs/reports/<lens>/<LENS>-REPORT-<YYYY-MM-DD>.md --badges tier

Writes `<same path>.html` and prints where it went. `--badges tier` for the
Critical/Major/Minor vocabulary every lens but `gof` uses, `grade` for `gof`'s
A–F pattern grades, `both` (the default) to badge either.

## Why a script and not a spec

- **A template change is one edit, not N.** The section→card mapping is coupled
  to the report template's shape; when the tiered container was renamed
  `## Recommendations` → `## Findings`, a per-lens spec had to be chased.
- **It is checkable.** Prose describing a colour is a guard nothing can verify;
  `tests/test_report_html.py` pins the escaping, the anchors, the badges and the
  self-containment.
- **It costs no model time.** Deterministic rendering was being paid for in
  tokens, once per report.

## The rules the artifact still has to meet

- **Self-contained** — inline CSS, no CDN, no external font, no remote image, no
  required JavaScript. It opens from a `file://` path with no server. The only
  script is nav highlighting, and the page is complete without it.
- **Gitignored** — it is an artifact, written beside a report that is already
  under a git-excluded `docs/reports/` directory. It is never the deliverable;
  the Markdown is.
- **Written after the Markdown exists**, never instead of it.

## Opt-in, per run

Rendering is offered, not automatic — a lens run that writes an HTML file nobody
asked for has spent the operator's disk and attention on a second copy of what
they already have. Under the `code-quality` umbrella it is offered once, for the
consolidated report, rather than six times for the lens reports it merged.

## Adding a vocabulary

Badges are data: a `BadgeRule` list passed to `render_html`. A lens that badges
something neither tier nor grade covers adds a rule list at its call site; the
renderer does not change.
