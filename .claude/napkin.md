# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each backlog item includes date + "Do instead".
- **Backlog order:** impact + dependencies (not FIFO). Data/training integrity first, then shared code, then tagging logic, then UI, then structural refactors.

## Backlog (Claude Code)

Ordered by impact and what unblocks what (not conversation order).

- [ ] **[2026-05-20] Fix `tagger_flask` commit → `examples.json` placeholders**
  Do instead: in `/commit` (~L762–776), stop appending hardcoded `"from": "(web)"`, `"subject": "(web)"`, `"snippet": ""`. Resolve each `email_id` from `raw_decisions` against session `EMAILS` (or re-fetch) and persist real `from`, `subject`, `snippet`, plus `id`/`email_id`.

- [ ] **[2026-05-20] Skip already-processed emails in `examples.json`**
  Do instead: before appending, check `email_id` (or stable key) against existing entries; skip duplicates. Depends on commit path saving real ids.

- [ ] **[2026-05-20] `tagger_flask`: mark inbox rows already in `examples.json`**
  Do instead: after fetch (sync + background batches), match each message to `examples.json` (prefer `email_id`, else from+subject); set row status to non-pending (e.g. `skipped` / `already_processed`) with clear label. Email stays unread in Gmail — only UI state reflects prior training.

- [ ] **[2026-05-20] `tagger_flask` FIXME: loading bar stuck after background fetch**
  Do instead: when `_fetch_state["done"]` is true, client must call `updateLoadingBar(..., done=true)` (spinner off, “done” styling). Fix `init()` forcing `done=false` (L545), last `/api/more` poll edge cases, and/or one final `/api/status` after `clearInterval`.

- [ ] **[2026-05-20] Deduplicate `fetch_emails`**
  Do instead: extract shared Gmail fetch/parsing into one module (e.g. `gmail_client.py`); remove copy-paste between `fetch_emails.py` and callers.

- [ ] **[2026-05-20] `auto_tag_email`: LLM similarity over regex for label choice**
  Do instead: in `auto_tagger.auto_tag_email`, rank/pick labels by similarity to LLM prompt examples first; regex secondary/fallback. Same sender may need tag-then-act when context matters.

- [ ] **[2026-05-20] Split HTML/CSS from `tagger_flask.py`**
  Do instead: move inline template (~L126–554) and `<style>` into `templates/` + `static/` (or equivalent); keep Flask routes thin. Easier UI tweaks after this.

- [ ] **[2026-05-20] Two-line rows in `tagger_flask` review table**
  Do instead: render each email on two lines (or wrap) so `subject`, `snippet`, and `reasoning` are readable. Prefer doing in extracted CSS once split is done.
