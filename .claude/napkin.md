# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each backlog item includes date + "Do instead".
- **Backlog order:** impact + dependencies (not FIFO). Data/training integrity first, then shared code, then tagging logic, then UI, then structural refactors.

## Backlog (Claude Code)

Ordered by impact and what unblocks what (not conversation order).

- [x] **[2026-05-20] Fix `tagger_flask` commit → `examples.json` placeholders**
  Do instead: in `/commit` (~L762–776), stop appending hardcoded `"from": "(web)"`, `"subject": "(web)"`, `"snippet": ""`. Resolve each `email_id` from `raw_decisions` against session `EMAILS` (or re-fetch) and persist real `from`, `subject`, `snippet`, plus `id`/`email_id`.

- [x] **[2026-05-20] Skip already-processed emails in `examples.json`**
  Do instead: before appending, check `email_id` (or stable key) against existing entries; skip duplicates. Depends on commit path saving real ids.

- [ ] **[2026-05-20] `tagger_flask`: mark inbox rows already in `examples.json`**
  Do instead: after fetch (sync + background batches), match each message to `examples.json` (prefer `email_id`, else from+subject); set row status to non-pending (e.g. `skipped` / `already_processed`) with clear label. Email stays unread in Gmail — only UI state reflects prior training.

- [ ] **[2026-05-20] `tagger_flask` FIXME: loading bar stuck after background fetch**
  Do instead: when `_fetch_state["done"]` is true, client must call `updateLoadingBar(..., done=true)` (spinner off, “done” styling). Fix `init()` forcing `done=false` (L545), last `/api/more` poll edge cases, and/or one final `/api/status` after `clearInterval`.

- [ ] **[2026-05-20] `tagger_flask`: last-action timestamp (fetch + commit)**
  Do instead: one dashboard field (e.g. near loading bar / summary) updated on each event with action label + local time: (1) first sync fetch finished, (2) background fetch finished, (3) commit completed. Single “last activity” line so user sees dashboard freshness; server can expose timestamps in `_fetch_state` / commit response, client updates on poll + commit success.

- [ ] **[2026-05-20] `tagger_flask`: opt-in background fetch + persist pending LLM suggestions**
  Today: after 1st batch loads, `_background_fetch` auto-runs `auto_tag_email` for every remaining unread (LLM keeps busy). Change flow so user controls continuation and work isn’t lost.
  - [ ] **1) Dashboard control: fetch next batch?**
    Do instead: add top-of-page control (toggle / “Load next batch” / Yes-No) after 1st sync batch; do not start `_background_fetch` (and LLM tagging for batch 2+) until user confirms. Each confirm loads one more `BATCH_SIZE` (or explicit “load all” if desired later).
  - [ ] **2) Persist suggestions for still-pending rows**
    Do instead: when `auto_tag_email` returns `action` + `reasoning`, save per `email_id` (e.g. `pending_suggestions.json` or session store) even if row status stays `pending` and email isn’t in `examples.json` yet. Reload on refresh so LLM suggestions/reasons survive without re-calling the LLM; distinct from “already processed” in `examples.json`.
  Do instead (parent): gate background fetch+tag on user consent; cache LLM output for pending rows by message id.

- [ ] **[2026-05-20] Tag picker UX (`tagger_flask` + `tagger_cli`)**
  Improve manual tagging: use LLM suggestions in the picker, filter in modal, shared label ordering.
  - [ ] **1) Pre-fill suggested tags in `tagger_flask` Pick modal**
    Do instead: on `openTagModal(idx)`, pre-select options from `DECISIONS[idx].action` (`tag:…` labels). User sees the same tags the auto-suggester proposed before confirming or editing.
  - [ ] **2) Filter labels in Flask tag modal**
    Do instead: add search/filter input on `#tagModal` (like CLI `pick_labels` filter step in `review_emails.py`); narrow `<select>` options as user types.
  - [ ] **3) Order labels: top-N frequent, then A–Z**
    Do instead: extract shared helper from `get_recent_labels` + sort (e.g. `ordered_labels_for_picker(examples, session, label_map, top_n=9)`): top-N by usage in `examples.json` + session first, remaining labels alphabetical. Use in `pick_labels()` (`tagger_cli`) and when building `LABELS` / `openTagModal` (`tagger_flask`).
  Do instead (parent): reuse `review_emails` ordering/filter logic in both interfaces so tag picking matches CLI behavior.

- [ ] **[2026-05-20] Deduplicate `fetch_emails`**
  Do instead: extract shared Gmail fetch/parsing into one module (e.g. `gmail_client.py`); remove copy-paste between `fetch_emails.py` and callers.

- [ ] **[2026-05-20] `auto_tag_email`: LLM similarity over regex for label choice**
  Do instead: in `auto_tagger.auto_tag_email`, rank/pick labels by similarity to LLM prompt examples first; regex secondary/fallback. Same sender may need tag-then-act when context matters.

- [ ] **[2026-05-20] Split HTML/CSS from `tagger_flask.py`**
  Do instead: move inline template (~L126–554) and `<style>` into `templates/` + `static/` (or equivalent); keep Flask routes thin. Easier UI tweaks after this.

- [ ] **[2026-05-20] Two-line rows in `tagger_flask` review table**
  Do instead: render each email on two lines (or wrap) so `subject`, `snippet`, and `reasoning` are readable. Prefer doing in extracted CSS once split is done.
