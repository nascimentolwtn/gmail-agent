# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each backlog item includes date + "Do instead".
- **Backlog order:** impact + dependencies (not FIFO). Data/training integrity first, then shared code, then tagging logic, then UI, then structural refactors.

## Backlog (Claude Code)

Ordered by impact and what unblocks what (not conversation order).

- [ ] **[2026-05-20] `tagger_flask`: loading progress only while fetching + beside “Load next batch”**
  Do instead: hide or stop showing `⏳ Loading emails… N / ~T loaded so far — review while you wait!` when idle (first batch done, waiting on user). Show it only while `/api/fetch_next` is in flight (`fetchSpinner` / `fetching` flag). Move progress text into `#fetchControl` next to `#btnFetchNext` (not `#loadingBar`); keep `#loadingBar` for errors / “all loaded” or remove redundant spinner when opt-in fetch is the only background path (`templates/dashboard.html` `updateLoadingBar`, `fetchNextBatch`, `updateFetchControl`).

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

- [x] **[2026-05-20] Tag picker modal polish (`tagger_flask`)**
  Fixed:
  - **Separator**: server passes `top_n` (count of frequent labels). `renderLabelOptions` inserts a disabled `────` option between the last "frequent" label and the first A–Z label. When filter narrows the list, separator still appears at the correct boundary.
  - **Sticky multi-select**: `modalSelectedTags` Set persists across filter re-renders. `renderLabelOptions` restores `opt.selected = true` for Set members. `syncModalSelection()` on `<select onchange>` updates the Set from DOM. `confirmTagPick` reads from the Set, not DOM `selectedOptions` — so filtering + picking works seamlessly.

- [x] **[2026-05-20] Deduplicate `fetch_emails.py` (in-file only)**
  Fixed: extracted `_message_to_email(service, msg, body_chars)` helper (lines 6–39). Both `get_unread_emails` and `get_unread_emails_paginated` now call it — each keeps its own list/pagination logic. ~40 lines of duplication removed.

- [x] **[2026-05-20] `auto_tag_email`: LLM similarity over regex for label choice**
  Fixed: refactored `_rule_based_tag` to score each *label* independently (not atomic actions). Labels within `label_threshold`×(top_score) are all returned, enabling multi-label and same-sender-different-tag behavior. Delete only wins when it outscores all tags combined (strong-signal gate). Per-label scores included in reason string.

- [x] **[2026-05-20] Split HTML/CSS from `tagger_flask.py`**
  Fixed: removed inline `DASHBOARD_HTML` string (~170 lines) and `<style>` block from Python. `tagger_flask.py` now uses `render_template("dashboard.html")` + `static/styles.css`. All JS logic (suggestions, fetch-next, dedup) preserved in template. Fixed missing `import os`. Made `tr.already-processed` visually distinct (blue `#e3f2fd`) from `tr.committed` (green `#e8f5e9`).

- [x] **[2026-05-20] Two-line rows in `tagger_flask` review table**
  Fixed: used `<colgroup>` with explicit `<col>` widths for stable column layout (`table-layout: fixed`). Applied `-webkit-line-clamp: 2` on inner `<div>` wrappers inside `.subject`, `.snippet`, `.reasoning` cells — never on `<td>` directly (breaks table-cell display). Column widths: # 2.5rem, From 11rem, Subject 20rem, Snippet 9rem, Suggestion 10rem, Reasoning 15rem, Actions 7rem, Status 6rem. Increased JS reasoning truncation from 120 to 200 chars.
