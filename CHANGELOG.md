# Changelog

## v1.0.0 — 2026-05-22

First stable release. A Gmail email review and tagging toolkit with both CLI and web interfaces, backed by an LLM-powered auto-tagger that learns from your examples.

### Architecture

- **Monolithic service pattern**: all Gmail API logic lives in focused single-purpose modules
- **Two interfaces**: terminal CLI (`tagger_cli.py`) and Flask web dashboard (`tagger_flask.py`) sharing the same core
- **LLM auto-tagger**: content-similarity scoring against your `examples.json` training data, not just naive regex rules
- **Dual Gmail scopes**: `gmail.readonly` + `gmail.modify` (read, label, delete)

### Modules

| File | Purpose |
|---|---|
| `auth_test.py` | OAuth2 authentication flow, token caching in `token.json` |
| `fetch_gmail_labels.py` | Fetch all Gmail labels for the authenticated account |
| `fetch_emails.py` | Fetch unread emails with pagination support; body extraction with text/plain → text/html → snippet fallback chain |
| `auto_tagger.py` | LLM-powered labeling: few-shot prompt from `examples.json`, per-label similarity scoring, multi-label and delete-gate logic |
| `suggest.py` | Lightweight label suggestion helper |
| `review_emails.py` | Terminal-based email review CLI |
| `tagger_cli.py` | Full CLI tagger: fetches unread emails, shows LLM suggestions, accepts interactive tag/delete/accept actions, commits to Gmail |
| `tagger_flask.py` | Flask web dashboard on port 5050: background batch fetching, LLM-powered review table, tag picker modal, commit to Gmail |

### Core Features

**Authentication & Email Fetch**
- Browser-based OAuth2 flow with refresh-token persistence (`token.json`)
- Paginated Gmail API fetching with `next_page_token` handling
- Robust body extraction: tries text/plain, falls back to text/html, falls back to snippet
- Body preview up to 300 characters stored per email

**Auto-Tagging Engine**
- Few-shot LLM prompting from `examples.json` (sender + subject + snippet + prior tag)
- Per-label scoring with threshold-based multi-label selection
- Delete wins only when it outscores all tag labels combined (strong-signal gate)
- Per-label scores included in reasoning output
- Graceful zero-shot operation when no `examples.json` exists

**CLI Tagger (`tagger_cli.py`)**
- Interactive terminal review of unread emails
- LLM-suggested actions displayed per email (accept / delete / tag)
- Manual tag picking with label filter and frequency-ordered label list
- Commit saves real Gmail `id`, `from`, `subject`, `snippet` per decision
- Duplicate prevention: skips emails already present in `examples.json`

**Flask Web Dashboard (`tagger_flask.py`)**
- Server-side template (`templates/dashboard.html` + `static/styles.css`) — no inline HTML/CSS
- Table layout with fixed columns: #, From, Subject, Snippet, Suggestion, Reasoning, Actions, Status
- Two-line cell clamping for Subject, Snippet, and Reasoning columns
- Background batch fetching with opt-in "Load next batch" button
- Auto-fetch of first batch on page load
- `pending_suggestions.json`: persists LLM output per `email_id` so suggestions survive page refresh
- Row state visualization:
  - White = pending review
  - Orange (`#fff3e0`) = pending commit (accepted/tagged/delete)
  - Green (`#e8f5e9`) = committed to `examples.json`
  - Blue (`#e3f2fd`) = already processed (exists in `examples.json` from prior session)
  - Dimmed = skipped
- Loading bar with spinner, status text, and last-activity timestamp in a single row
- "Accept All Pending" button: bulk-accepts all rows with LLM suggestions
- Commit sends `from`, `subject`, `snippet` client-side to avoid server state issues

**Tag Picker Modal (Web)**
- Pre-fills with LLM-suggested tags on open
- Search/filter input narrows label list in real-time
- Label ordering: top-N most frequent (from `examples.json` + current session), then alphabetical
- Visual separator between frequent and alphabetical sections
- Sticky multi-select: selections persist across filter re-renders via `modalSelectedTags` Set + `rebuilding` flag

### Bug Fixes (all reaching correctness for v1.0)

- **Duplicate rows**: fixed `last_served_idx` for batch 0, passed `next_page_token` to background fetch, added JS-side `addBatch` dedup by `email.id`
- **`examples.json` crash**: `load_examples()` returns `[]` for missing file or non-list JSON root
- **Placeholder commit data**: `/commit` now resolves real `from`/`subject`/`snippet` from session data (or client-supplied fields) instead of `"(web)"`
- **Loading bar stuck**: fixed `init()` forcing `done=false`, last-poll edge cases, and final `/api/status` call
- **Loading bar missing during user fetch**: `fetchNextBatch()` now calls `updateLoadingBar` immediately with "Loading emails…" state
- **Tag modal selection corruption**: browser `onchange` events during programmatic `<select>` rebuilds corrupted `modalSelectedTags`; fixed with `rebuilding` flag guard
- **Suggestion column stale after tag pick**: `confirmTagPick()` now sets both `state[idx].action` and `DECISIONS[idx].action`; `acceptRow()` preserves user-set actions
- **`dict + list` TypeError**: normalized across all loaders — non-list JSON roots convert to `[]`
- **`fetch_emails.py` duplication**: extracted `_message_to_email()` helper, ~40 lines removed
- **Green highlight visibility**: `already-processed` rows use distinct blue instead of opacity-reduced grey

### Pending (post-v1.0 backlog)

- "Hide Already-Processed/Committed" toggle button
- Android app: local-LLM Gmail tagger with Jetpack Compose + TinyLlama
- Per-credential `examples.json` namespaced by `project_id` for multi-account safety
- Post-commit LLM email body summaries

### Dependencies

- `google-api-python-client` — Gmail API
- `google-auth-oauthlib` — OAuth2 flow
- `google-auth-httplib2` — HTTP transport

### Security Notes

- `token.json`, `credentials.json`, `client_secret_*.json`, `examples_*.json`, `pending_suggestions.json` are all `.gitignore`d
- Never commit credential or token files
