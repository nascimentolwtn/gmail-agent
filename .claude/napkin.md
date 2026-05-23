# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each backlog item includes date + "Do instead".
- **Backlog order:** impact + dependencies (not FIFO). Data/training integrity first, then shared code, then tagging logic, then UI, then structural refactors.

## Backlog (Claude Code)

Ordered by impact and what unblocks what (not conversation order).

- [x] **[2026-05-20] `tagger_flask`: loading progress only while fetching + beside "Load next batch"**
  Fixed: moved status text into `#fetchControl` next to `#btnFetchNext`. `updateLoadingBar()` manages all 3 states (done/fetching/idle) and controls fetch control visibility. Loading bar at top shows minimal status; detail text lives in fetch control row.

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
  Do instead: when `_fetch_state["done"]` is true, client must call `updateLoadingBar(..., done=true)` (spinner off, "done" styling). Fix `init()` forcing `done=false` (L545), last `/api/more` poll edge cases, and/or one final `/api/status` after `clearInterval`.

- [x] **[2026-05-20] `tagger_flask`: last-action timestamp (fetch + commit)**
  Fixed: added `last_activity` to `_fetch_state` with `{action, ts}` recorded on first_batch, fetch_batch, fetch_complete, and commit. Exposed via `/api/status` and commit response. Client shows "⏳ First batch loaded at HH:MM:SS" etc. in `#lastActivity` div below loading bar.

- [x] **[2026-05-20] `tagger_flask`: opt-in background fetch + persist pending LLM suggestions**
  Fixed:
  - Removed auto-start of `_background_fetch` in `dashboard()`. Instead stores `next_page_token` in `_fetch_state` and sets `done=true` immediately if no more pages.
  - Added `/api/fetch_next` (POST) endpoint: fetches one `BATCH_SIZE` batch, tags via LLM, appends to `batches`, returns new emails+decisions. Dashboard shows "Load next batch" button with remaining count; hides when all fetched.
  - Added `pending_suggestions.json` + `_load_pending_suggestions()` / `_save_pending_suggestions()` helpers. Each fetched batch's LLM output (action+reasoning) is persisted per `email_id`.
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

- [x] **[2026-05-21] FIXME: Suggestion column not updated when overriding delete with tag**
  Fixed: `confirmTagPick()` now sets both `state[modalRowIdx].action` and `DECISIONS[modalRowIdx].action` to the new tag array. Since `updateRowUI()` reads `s.action || DECISIONS[idx].action` and `confirmTagPick()` overwrites `s.action` first, the `||` always picks up the new tag action. `acceptRow()` also fixed to preserve user-set actions via `cur.action || DECISIONS[idx].action`.

- [x] **[2026-05-20] Tag picker modal polish (`tagger_flask`)**
  Fixed:
  - **Separator**: server passes `top_n` (count of frequent labels). `renderLabelOptions` inserts a disabled `────` option between the last "frequent" label and the first A–Z label. When filter narrows the list, separator still appears at the correct boundary.
  - **Sticky multi-select**: `modalSelectedTags` Set persists across filter re-renders. `renderLabelOptions` restores `opt.selected = true` for Set members. `handleSelectChange` on `<select onchange>` diffs visible vs selected to preserve hidden selections. `confirmTagPick` reads from the Set, not DOM `selectedOptions`.
  - **FIXME (still broken)**: after filtering labels and selecting labels that are visible in the filtered list, clearing the textbox causes selected labels to become unselected. Root cause: `renderLabelOptions` rebuilds the `<select>` DOM and sets `opt.selected = true` via `makeOption`, which fires the `onchange` event. `handleSelectChange` then reads `sel.selectedOptions` — but during the rebuild the DOM selection state is inconsistent, causing items to be removed from `modalSelectedTags`. Fix: use a `rebuilding` flag to suppress `handleSelectChange` during programmatic re-renders, or detach/reattach the `onchange` handler around `renderLabelOptions` calls.
    **Fixed (2026-05-22)**: added `rebuilding` flag, set `true` at start of `renderLabelOptions` and `false` at end. `handleSelectChange` early-returns when `rebuilding` is true. This also fixes the downstream "suggestion column not updated" bug since `modalSelectedTags` is no longer corrupted during render.

- [x] **[2026-05-20] Deduplicate `fetch_emails.py` (in-file only)**
  Fixed: extracted `_message_to_email(service, msg, body_chars)` helper (lines 6–39). Both `get_unread_emails` and `get_unread_emails_paginated` now call it — each keeps its own list/pagination logic. ~40 lines of duplication removed.

- [x] **[2026-05-20] `auto_tag_email`: LLM similarity over regex for label choice**
  Fixed: refactored `_rule_based_tag` to score each *label* independently (not atomic actions). Labels within `label_threshold`×(top_score) are all returned, enabling multi-label and same-sender-different-tag behavior. Delete only wins when it outscores all tags combined (strong-signal gate). Per-label scores included in reason string.

- [x] **[2026-05-20] Split HTML/CSS from `tagger_flask.py`**
  Fixed: removed inline `DASHBOARD_HTML` string (~170 lines) and `<style>` block from Python. `tagger_flask.py` now uses `render_template("dashboard.html")` + `static/styles.css`. All JS logic (suggestions, fetch-next, dedup) preserved in template. Fixed missing `import os`. Made `tr.already-processed` visually distinct (blue `#e3f2fd`) from `tr.committed` (green `#e8f5e9`).

- [x] **[2026-05-20] Two-line rows in `tagger_flask` review table**
  Fixed: used `<colgroup>` with explicit `<col>` widths for stable column layout (`table-layout: fixed`). Applied `-webkit-line-clamp: 2` on inner `<div>` wrappers inside `.subject`, `.snippet`, `.reasoning` cells — never on `<td>` directly (breaks table-cell display). Column widths: # 2.5rem, From 11rem, Subject 20rem, Snippet 9rem, Suggestion 10rem, Reasoning 15rem, Actions 7rem, Status 6rem. Increased JS reasoning truncation from 120 to 200 chars.

- [x] **[2026-05-21] Loading bar not showing "Loading emails…" during user-initiated "Load next batch"**
  Fixed: `fetchNextBatch()` and `startBackgroundFetch()` now call `updateLoadingBar(null, null, false, null, null, true)` immediately before the fetch, so "⏳ Loading emails…" shows right away. Added `_lastLoaded`/`_lastTotal` module-level vars so passing `null` preserves last known values. After fetch completes, `updateLoadingBar(data.loaded, data.total, data.done, data.error, data.last_activity, false)` switches back to idle state.

- [x] **[2026-05-21] Suggestion column not updated after picking tags in modal**
  Fixed (2026-05-22): `confirmTagPick()` now reads directly from DOM `sel.selectedOptions` instead of the `modalSelectedTags` Set (which could be corrupted by `handleSelectChange` during `renderLabelOptions` rebuilds). Also added `rebuilding` flag to suppress `handleSelectChange` during programmatic re-renders. `updateRowUI()` uses `row.querySelector('.suggestion')` instead of positional `row.children[4]`. Column header renamed to "Suggestion/Selection".

- [x] **[2026-05-21] Commit saves `from`, `subject`, `snippet` from client**
  Fixed: JS `commitAll()` now sends `from`, `subject`, `snippet` with each decision from the client-side `EMAILS` array. Server save logic prefers client-provided fields over fragile `_fetch_state` batch lookup. Eliminates empty-field bug caused by multi-worker Flask or page refreshes clearing server state.

- [x] **[2026-05-21] Row background color for pending-commit (accepted/tagged/delete)**
  Fixed: added `tr.pending-commit { background: #fff3e0; }` (orange/amber) and `.status-pending-commit { color: #e65100; }` in CSS. `updateRowUI()` now applies `pending-commit` class for accepted/delete/tagged rows and shows "⏳ accepted" / "⏳ delete" / "⏳ tagged" in the status cell. Distinct from `committed` (green), `already-processed` (blue), and `skipped` (dimmed).

- [x] **[2026-05-21] Auto background fetch one batch on page load**
  Fixed: `init()` calls `startBackgroundFetch()` which fetches one batch via `/api/fetch_next` with button disabled + spinner. After completion, button re-enabled, loading bar and fetch control updated. Removed old `updateFetchControl()` function — logic folded into `updateLoadingBar()`.

- [x] **[2026-05-21] Loading bar and timestamp merged into one row**
  Fixed: `#lastActivity` moved inside `#loadingBar` div. Layout: `[spinner] [status text..............] [timestamp right-aligned]`. `loadingText` gets `flex:1` to expand and push timestamp to the right edge.

- [x] **[2026-05-21] Fix column widths — more room for Snippet, less for Subject**
  Fixed: adjusted `<colgroup>` widths: Subject 20rem → 13rem, Snippet 9rem → 16rem. Snippet column now has much more room for body text while Subject is narrower (subject lines are typically short).

- [x] **[2026-05-21] "Accept All Pending" button**
  Fixed: added `✓ Accept All Pending` button (green `#34a853`) in toolbar between "Commit All" and "Refresh". `acceptAllPending()` iterates all rows with `status==='pending'`, sets `delete` for delete suggestions and `accepted` for everything else, skips rows with no suggestion. Calls `updateRowUI()` per row so rows go to pending-commit (orange) state. Toast confirms count or "no pending rows".

- [x] **[2026-05-23] Confirmation modal on "Accept All Pending"**
  Fixed: added `#acceptAllModal` overlay with "Are you sure?" question. `showAcceptAllConfirm()` counts pending rows first; if zero, shows toast immediately. Otherwise shows modal. `confirmAcceptAll()` performs the actual accept-all after user confirms. Reuses existing `.modal-overlay`/`.modal` CSS patterns.

- [X] **[2026-05-21] "Hide Already-Processed/Committed" toggle button**
  Do instead: add a toggle button "Hide Already-Processed" in the toolbar. First click hides all rows that are `already-processed` or `committed` (adds CSS class `.row-hidden { display: none }` to `<tr>` elements). Second click shows them again (removes the class). Rows stay in the DOM and in `EMAILS`/`DECISIONS` arrays — purely visual toggle, no data removal. Button text toggles between "Hide Already-Processed" and "Show All". Hidden rows keep their original index numbers (no renumbering). State persists across background fetches — new batches re-evaluate visibility based on current toggle state.

- [x] **[2026-05-23] Summary modal always showing "unknown" for subject/from**
  Root cause: `summarize_email_bodies()` never included email IDs in the LLM prompt (only `Email 1:`, `Email 2:` etc.), so the LLM couldn't return correct ID keys. `showSummaryModal()` then failed to find emails in `emailMap`, showing `'(unknown)'` for subject and empty string for `from`.
  Fix: changed prompt to use positional indices (`"1"`, `"2"`, …) as keys and map them back to actual email IDs server-side after the LLM response. The `emailMap` lookup in `showSummaryModal` now works correctly, displaying real `from` and `subject` values.

- [ ] **[2026-05-23] Skip LLM tagging for emails already trained in examples.json — replay saved action instead**
  Currently `auto_tag_email()` is called for every email on every fetch (both `/` and `/api/fetch_next`), even if that email was already committed to `examples.json`. For already-trained emails, the LLM call is wasted and can even suggest a *different* action than what the user previously chose.

  Do instead:
  1. Before calling `auto_tag_email()`, look up the email in `examples.json` (match by `id` first, fall back to `from+subject` composite key).
  2. If found, build an `EmailDecision` directly from the saved entry: `action = ex["action"]` (e.g. `"delete"` or `["tag:LABEL1", ...]`), `reasoning = ex.get("reasoning", "previously trained")`, and restore `mark_read` / `delete_later` booleans from the saved entry.
  3. For the **client-side** `addBatch()` / `isAlreadyProcessed()` flow: already-processed rows currently get the *LLM suggestion* as their `DECISIONS[idx].action` and the saved action only in `state[idx].action` (via `processed ? null : …`). Fix this so that the saved action from examples.json is also placed in `DECISIONS[idx]` — that way the suggestion badge shows what was *actually* done before, not a new LLM guess. The `state[idx].action` for already-processed rows should also be set to the saved action (not `null`), so the row accurately reflects the prior decision.
  4. For the **server-side** batch data sent to the client: when an email matches examples.json, include the saved action+reasoning in the batch response so the client can populate `DECISIONS` and `state` correctly. Both first batch (dashboard route) and background batches (fetch_next route) need this.
  5. In `dashboard()` route (~L178-194): pass the `already_ids`/`already_keys` sets to the tagging loop, and for matched emails skip the LLM call.
  6. In `api_fetch_next()` (~L348-361): same — check examples.json before calling `auto_tag_email()`.

  Depends on: nothing. Unblocks skipping wasted LLM calls and showing correct prior actions in the suggestion column.

- [ ] **[2026-05-22] Redesign tag picker modal: click-to-add / ✕-to-remove list instead of ctrl+click `<select multiple>`**
  Replace the current `<select multiple>` in the tag picker modal with a clickable list UI. Each visible label is a row with the label name on the left and an "✕" button on the left. Clicking the label name selects/adds the tag (highlights it, adds to chosen set). Clicking "✕" on a chosen tag removes it. Selected tags appear in a "Chosen" section at the top of the list (or inline with a distinct style). The filter input still filters the full label list. No ctrl+click needed — single click toggles. Update CSS and JS (`openTagModal`, `renderLabelOptions`, `confirmTagPick`, remove `handleSelectChange`/`modalSelectedTags` Set/dedup logic, remove `rebuilding` flag).

- [ ] **[2026-05-22] Android app: local-LLM Gmail tagger**
  Build an Android app replicating `tagger_flask.py` features (email fetch, auto-tag review, commit) but using a local LLM (TinyLlama) for reasoning instead of a remote API. Key sub-tasks:
  - **Gmail auth on Android**: OAuth2 via Google Sign-In SDK (replaces `auth_test.py` browser flow). Scopes: `gmail.readonly` + `gmail.modify`.
  - **Email fetch**: port `fetch_emails.py` pagination logic to Kotlin/Java using Gmail API client library for Android.
  - **Local LLM inference**: bundle TinyLlama (GGUF ~600MB) via `llama.cpp` Android bindings or MediaPipe LLM runtime. Replace `auto_tag_email()` / `pick_labels_from_prompt()` calls with on-device inference. Prompt format unchanged — same few-shot examples from `examples.json`.
  - **UI**: single-activity + Jetpack Compose. Email list with swipe-to-accept/delete, tag picker modal (mirror Flask dashboard UX), commit button. Offline-capable: queue commits if no network.
  - **Examples sync**: import/export `examples.json` so training data can be seeded from desktop `tagger_flask` session.
  - **Stretch**: on-device summarization (post-commit body summaries item) using same TinyLlama instance.
  Stack: Kotlin + Jetpack Compose + Google Sign-In + Gmail API client + llama.cpp NDK or MediaPipe.

- [ ] **[2026-05-22] Per-credential `examples.json` (keyed by `project_id`)**
  Do instead: when multiple `credentials.json` files exist (different Google Cloud projects / Gmail accounts), each project gets its own examples file so training data doesn't leak across accounts. Flow:
  1. On startup, read `credentials.json` (or the active cred file) and extract `project_id` (e.g. `"luizwagnerlwtn"`).
  2. Derive examples filename: `examples_{project_id}.json` (e.g. `examples_luizwagnerlwtn.json`).
  3. All `load_examples()` / `save_examples()` calls across `auto_tagger.py`, `review_emails.py`, `tagger_flask.py`, `tagger_cli.py`, and `suggest.py` use the derived filename instead of hardcoded `"examples.json"`.
  4. `pending_suggestions.json` in `tagger_flask.py` should also be namespaced: `pending_suggestions_{project_id}.json`.
  5. Add a migration helper: if `examples.json` exists but no `examples_{project_id}.json` does, copy/rename it on first run.
  6. Update `.gitignore` to `examples_*.json` and `pending_suggestions_*.json`.
  Depends on: nothing. Unblocks safe multi-account usage.

- [x] **[2026-05-22] "Mark as Read" and "Delete Later" checkboxes**
  Fixed: added "Options" column with "Read" and "Del Later" checkboxes per row. `toggleMarkRead(idx, checked)` sets `state[idx].mark_read`. `toggleDeleteLater()` enforces mutual exclusion with delete action (reverts delete → pending/skipped). `deleteRow()` unchecks Del Later checkbox + state. `commitAll()` sends both booleans in payload. `api_commit()` removes UNREAD label when `mark_read=true`, skips trash when `delete_later=true`. Both fields saved to `examples.json`. State preserved across all row-action transitions.

- [x] **[2026-05-21] Post-commit LLM email body summaries**
  Fixed:
  - Added `summarize_email_bodies()` in `auto_tagger.py` — batches all non-deleted committed emails into one LLM call using the same `LLAMA_URL` pattern as `pick_labels_from_prompt`. Returns `{email_id: summary}` dict. Gracefully returns `{}` if LLM unavailable.
  - `tagger_flask.py` `/commit` endpoint: after saving examples, builds summary inputs from non-deleted decisions, calls `summarize_email_bodies()`, includes `summaries` in JSON response.
  - `templates/dashboard.html`: added `#summaryModal` overlay. `commitAll()` checks `data.summaries` and calls `showSummaryModal()` to display subject + from + summary per email. `closeSummaryModal()` dismisses.
  - `tagger_cli.py`: after save_examples, builds summary inputs, calls `summarize_email_bodies()`, prints `📝 Body Summaries:` with `• <subject>: <summary>` per email before the commit stats block.
