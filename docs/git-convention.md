# Plugin convention — skills that modify a codebase

This applies to **every skill in this plugin that edits, creates, or deletes
files in a user's codebase** (today: `solid` and `tdd`; any future code-modifying skill
adopts it by linking this file from its SKILL.md). Report/document generators
that only add gitignored artifacts are exempt.

The point: the user should always be able to review, land, or discard a
skill's work as one clean unit — and nothing a skill does should ever reach a
shared branch or remote without them saying so.

## Before the first file modification: open a working branch

- Target is a git repo and you're on the default branch (`main`/`master`) →
  create and switch to a working branch **before touching any file**:
  `<skill-name>/<short-slug>` (e.g. `solid/dedupe-discounts-2026-07-06`).
- Already on a feature branch → stay on it, but say so — the user may be
  mid-work and prefer a fresh branch off it.
- Dirty working tree → list the already-modified files first and keep the
  skill's changes from mixing with them; if they overlap the files the skill
  must touch, stop and ask.
- Not a git repo → say so and offer `git init`. If declined, proceed only
  after warning that there is no revert seam beyond the skill's own backups.

## After finishing: offer to commit and open a PR — never auto-publish

- **Offer, don't do.** Propose a Conventional Commit summarizing the work and
  ask whether to commit and raise a PR. "No, leave it on the branch" and
  "discard it" are first-class answers.
- On yes: this plugin's `/ship` skill is exactly this flow (branch → commit →
  push → PR with one confirmation before anything goes public) — prefer
  handing off to it. Without it, do the equivalent manually: commit on the
  working branch, push, `gh pr create`.
- Pushing and PR creation are outward-facing; they need an explicit yes in
  this session — a generic pre-authorization to "apply changes" covers edits,
  not publication.
