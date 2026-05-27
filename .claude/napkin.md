# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each item includes date + "Do instead".

## Backlog (Claude Code)

Ordered by impact and dependencies (not conversation order).

- [ ] **[2026-05-27] Skip LLM reasoning for already-trained tags**
  Do instead: before calling LLM, check if top rule-based match has high similarity (same sender + subject). If yes, return those tags directly. Only call LLM for novel/uncertain cases (low similarity scores).

- [X] **[2026-05-27] UI: Snippet truncate to 200 chars with "..." + 3-line hover hints**
  Do instead: (1) Truncate snippet to 197 chars + "..." = 200 total in dashboard.html buildRow(). (2) Add max-height: 4.5rem to .snippet/.reasoning CSS. (3) Hover hints via title attributes show full text. Generalized test_dashboard_rendering.py for future cell rendering checks.

- [ ] **[2026-05-22] Android app: local-LLM Gmail tagger**
  Plans saved:
  - Phase 1 MVP (rule-based, no LLM): `.claude/plans/this-backlog-will-be-wise-kite.md`
  - Phase 2 MediaPipe LLM integration: `.claude/plans/android-phase2-mediapipe-llm.md`
  Blocked on: Google Cloud Console — add Android OAuth client (package `com.libuy.gmailagent` + debug SHA-1), download `google-services.json`.
  Deploy: `./gradlew assembleDebug` + `adb install app-debug.apk`. Personal use only, no Play Store.

- [X] **[2026-05-22] Per-credential `examples.json` (keyed by `project_id`)**
  Do instead: extract `project_id` from `credentials.json`; derive `examples_{project_id}.json` and `pending_suggestions_{project_id}.json`. Update all `load_examples()`/`save_examples()` calls in `auto_tagger.py`, `review_emails.py`, `tagger_flask.py`, `tagger_cli.py`, `suggest.py`. Add migration helper on first run. Update `.gitignore` to `examples_*.json`.

## Domain Behavior Guardrails

1. **[2026-05-20] `examples.json` loaders must tolerate missing or non-list root**
   Do instead: all `load_examples()` calls return `[]` on missing file or non-list JSON root — never raise, never return `{}`.

2. **[2026-05-21] Commit must save real `from`/`subject`/`snippet` (not placeholders)**
   Do instead: JS `commitAll()` sends these fields from the client-side `EMAILS` array; server prefers client-provided fields over stale `_fetch_state` lookup.

3. **[2026-05-22] Tag picker `rebuilding` flag prevents `modalSelectedTags` corruption**
   Do instead: any time `renderLabelOptions()` rebuilds the DOM, set `rebuilding = true` before and `false` after; suppress `handleSelectChange` during rebuild.

## User Directives

1. **[2026-05-26] Don't manage git staging — user stages manually**
   Do instead: never run `git add` or `git add -A`; only commit/diff/status as needed.
