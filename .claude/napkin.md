# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each backlog item includes date + "Do instead".
- **Backlog order:** impact + dependencies (not FIFO). Data/training integrity first, then shared code, then tagging logic, then UI, then structural refactors.

## Backlog (Claude Code)

Ordered by impact and what unblocks what (not conversation order).

- [x] **[2026-05-20] URGENT FIXME: duplicate rows in `tagger_flask` email list**
  Fixed: (1) set `last_served_idx=1` after storing batch 0 so `/api/more` skips already-rendered rows; (2) pass `next_token` to `_background_fetch(start_page_token=…)` so it doesn't re-fetch page 1; (3) added JS-side `addBatch` dedup by `email.id` as safety net.

- [x] **[2026-05-20] `tagger_cli`: save Gmail `id` to `examples.json`**
  Verified: all CLI paths (accept/delete/tag) set `email_id`; `as_json()` always includes `"id"`. Entries in `examples.json` confirm ids present. Code already correct.

- [x] **[2026-05-20] Missing `examples.json` crashes `tagger_flask`**
  Do instead: `load_examples()` in `auto_tagger.py` (~L67) raises `FileNotFoundError` when file absent; return `[]` instead (or create `examples.json` as `[]` on first use). Dashboard and CLI must start with no training file — zero-shot tagging until user commits first example.

- [x] **[2026-05-20] FIXME: `pick_labels` / `ordered_labels_for_picker` — `dict` + `list` TypeError**
  Do instead: `review_emails.py` ~L30 `examples + session_decisions` crashes when `examples.json` is a JSON object (e.g. `{}`) not a list. Normalize in all loaders (`review_emails.load_examples`, `auto_tagger.load_examples`): missing file → `[]`, non-list root → `[]` or migrate. Repro: `review_emails` action `t` → `pick_labels` → `get_recent_labels`.

- [x] **[2026-05-20] Fix `tagger_flask` commit → `examples.json` placeholders**
  Do instead: in `/commit` (~L762–776), stop appending hardcoded `"from": "(web)"`, `"subject": "(web)"`, `"snippet": ""`. Resolve each `email_id` from `raw_decisions` against session `EMAILS` (or re-fetch) and persist real `from`, `subject`, `snippet`, plus `id`/`email_id`.

- [x] **[2026-05-20] Skip already-processed emails in `examples.json`**
  Do instead: before appending, check `email_id` (or stable key) against existing entries; skip duplicates. Depends on commit path saving real ids.

- [x] **[2026-05-20] `tagger_flask`: mark inbox rows already in `examples.json`**
  Do instead: after fetch (sync + background batches), match each message to `examples.json` (prefer `email_id`, else from+subject); set row status to non-pending (e.g. `skipped` / `already_processed`) with clear label. Email stays unread in Gmail — only UI state reflects prior training.

- [x] **[2026-05-20] `tagger_flask`: green highlight for already-processed / already-trained rows**
  Fixed: replaced `tr.already-processed` CSS (`#f8f9fa` + `opacity:0.6`) with clean `#e8f5e9` (same green as committed, but rows are visually distinct by context).

- [x] **[2026-05-20] `tagger_flask` FIXME: loading bar stuck after background fetch**
  Do instead: when `_fetch_state["done"]` is true, client must call `updateLoadingBar(..., done=true)` (spinner off, “done” styling). Fix `init()` forcing `done=false` (L545), last `/api/more` poll edge cases, and/or one final `/api/status` after `clearInterval`.

- [x] **[2026-05-20] `tagger_flask`: last-action timestamp (fetch + commit)**
  Fixed: added `last_activity` to `_fetch_state` with `{action, ts}` recorded on first_batch, fetch_batch, fetch_complete, and commit. Exposed via `/api/status` and commit response. Client shows “⏳ First batch loaded at HH:MM:SS” etc. in `#lastActivity` div below loading bar.

- [x] **[2026-05-20] `tagger_flask`: opt-in background fetch + persist pending LLM suggestions**
  Fixed:
  - Removed auto-start of `_background_fetch` in `dashboard()`. Instead stores `next_page_token` in `_fetch_state` and sets `done=true` immediately if no more pages.
  - Added `/api/fetch_next` (POST) endpoint: fetches one `BATCH_SIZE` batch, tags via LLM, appends to `batches`, returns new emails+decisions. Dashboard shows “Load next batch” button with remaining count; hides when all fetched.
  - Added `pending_suggestions.json` + `_load_pending_suggestions()` / `_save_pending_suggestions()` helpers. Each fetched batch’s LLM output (action+reasoning) is persisted per `email_id`.
  - Added `/api/suggestions` endpoint. `init()` calls it on load and merges cached suggestions into `DECISIONS` for rows that still have no action, so LLM work survives refresh without re-calling model.
  - `pending_suggestions.json` added to `.gitignore`.

- [x] **[2026-05-20] Tag picker UX (`tagger_flask` + `tagger_cli`)**
  Improve manual tagging: use LLM suggestions in the picker, filter in modal, shared label ordering.
  - [x] **1) Pre-fill suggested tags in `tagger_flask` Pick modal**
    Do instead: on `openTagModal(idx)`, pre-select options from `DECISIONS[idx].action` (`tag:…` labels). User sees the same tags the auto-suggester proposed before confirming or editing.
  - [x] **2) Filter labels in Flask tag modal**
    Do instead: add search/filter input on `#tagModal` (like CLI `pick_labels` filter step in `review_emails.py`); narrow `<select>` options as user types.
  - [x] **3) Order labels: top-N frequent, then A–Z**
    Do instead: extract shared helper from `get_recent_labels` + sort (e.g. `ordered_labels_for_picker(examples, session, label_map, top_n=9)`): top-N by usage in `examples.json` + session first, remaining labels alphabetical. Use in `pick_labels()` (`tagger_cli`) and when building `LABELS` / `openTagModal` (`tagger_flask`).
  Do instead (parent): reuse `review_emails` ordering/filter logic in both interfaces so tag picking matches CLI behavior.

- [ ] **[2026-05-20] Tag picker modal polish (`tagger_flask`)**
  - [ ] **1) Separator: top-N picks vs A–Z remaining tags **
    Do instead: in `#tagModal`, visual divider between frequent labels (`LABELS` / `ordered_labels_for_picker` top-N) and the rest — mirror CLI `pick_labels` section break (`review_emails.py` ~L67–68). Pass `top_n` or `recent_count` from server so `renderLabelOptions` can insert `<optgroup>` or a disabled separator option.
  - [ ] **2) Sticky multi-select across filter**
    Do instead: `renderLabelOptions` / `filterLabels` rebuild `<select>` and drop prior selections. Keep a `modalSelectedTags` `Set`; on toggle add/remove; on re-render restore `selected` for names in the set; `confirmTagPick` reads the set (not only visible `selectedOptions`).
  Do instead (parent): multi-tag workflow: pick one label, filter, pick another without losing the first.

- [ ] **[2026-05-20] Deduplicate `fetch_emails.py` (in-file only)**
  Do instead: no new module — extract shared loop body from duplicated blocks `fetch_emails.py` L17–53 and L119–153 into one helper (e.g. `_message_to_email_dict(service, msg_id, body_chars)` → dict or None + unreadable). `get_unread_emails` and `get_unread_emails_paginated` keep list/pagination logic; only message fetch + decode + dict build is shared.

- [ ] **[2026-05-20] `auto_tag_email`: LLM similarity over regex for label choice**
  Do instead: in `auto_tagger.auto_tag_email`, rank/pick labels by similarity to LLM prompt examples first; regex secondary/fallback. Same sender may need tag-then-act when context matters.

- [x] **[2026-05-20] Split HTML/CSS from `tagger_flask.py`**
  Fixed: removed inline `DASHBOARD_HTML` string (~170 lines) and `<style>` block from Python. `tagger_flask.py` now uses `render_template("dashboard.html")` + `static/styles.css`. All JS logic (suggestions, fetch-next, dedup) preserved in template. Fixed missing `import os`. Made `tr.already-processed` visually distinct (blue `#e3f2fd`) from `tr.committed` (green `#e8f5e9`).

- [ ] **[2026-05-20] Two-line rows in `tagger_flask` review table**
  Do instead: render each email on two lines (or wrap) so `subject`, `snippet`, and `reasoning` are readable. Prefer doing in extracted CSS once split is done.
