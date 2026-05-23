# Gmail Auto-Tagger

A Gmail email review and tagging toolkit with both CLI and web interfaces, powered by an LLM that learns from your examples.

## What It Does

Connects to your Gmail account, fetches unread emails, and uses an LLM to suggest tags (labels) or delete actions based on your past decisions. You review the suggestions, adjust as needed, and commit — the actions are applied to Gmail and saved as training data for next time.

**Two interfaces, one engine:**

- **Web Dashboard** (`tagger_flask.py`) — Flask app on port 5050 with a review table, tag picker modal, background batch fetching, and bulk actions
- **Terminal CLI** (`tagger_cli.py`) — interactive terminal review with the same LLM suggestions and commit flow

Both share the same auto-tagging engine and training data (`examples.json`).

## Quick Start

### 1. Install Dependencies

```bash
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 flask requests
```

### 2. Set Up Google OAuth Credentials

Follow these steps to create a `credentials.json` file that lets this project access your Gmail account:

**Step 1 — Create a Google Cloud project**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top of the page → **New Project**
3. Give it a name (e.g. `gmail-auto-tagger`) and click **Create**

**Step 2 — Enable the Gmail API**

1. In your new project, go to **APIs & Services** → **Library**
2. Search for **Gmail API** and click it
3. Click **Enable**

**Step 3 — Create an OAuth consent screen**

1. Go to **APIs & Services** → **OAuth consent screen**
2. Choose **User Type: External** (unless you're in a Google Workspace org) → **Create**
3. Fill in the required fields:
   - **App name**: `Gmail Auto-Tagger` (or whatever you prefer)
   - **User support email**: your email
   - **Developer contact info**: your email
4. Click **Save and Continue** through the Scopes step (no need to add extra scopes manually — the app requests them at runtime)
5. Add your own email as a **Test user** under the "Test users" section → **Save and Continue**
6. Review the summary and click **Back to Dashboard**

**Step 4 — Create OAuth client credentials**

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. If prompted to configure the consent screen first, go back to Step 3
4. Choose **Application type: Desktop app**
5. Give it a name (e.g. `gmail-auto-tagger-desktop`) → **Create**
6. A dialog appears with your client ID and client secret — click the **⬇ Download JSON** button
7. Save the downloaded file as `credentials.json` in the project root

**Step 5 — Authorize and generate `token.json`**

1. Run any script in the project (e.g. `python auth_test.py`)
2. A browser window opens asking you to sign in to Google and grant permissions
3. You may see a "Google hasn't verified this app" warning — click **Advanced** → **Go to \<project name\> (unsafe)**
4. Grant the requested Gmail permissions
5. The script saves a `token.json` in the project root. This file contains your refresh token and is reused automatically on subsequent runs — you won't need to authorize again unless you delete it

> **Important:** Both `credentials.json` and `token.json` are listed in `.gitignore`. Never commit these files — they contain secrets tied to your Google account.

### 3. Run

**Web dashboard:**

```bash
python tagger_flask.py
# Open http://localhost:5050
```

**Terminal CLI:**

```bash
python tagger_cli.py
```

On first run with no `examples.json`, the LLM operates in zero-shot mode. As you commit decisions, it learns from them — future suggestions improve automatically.

## Project Structure

| File | Purpose |
|---|---|
| `auth_test.py` | OAuth2 authentication flow, token caching |
| `fetch_emails.py` | Fetch unread emails with pagination and body extraction |
| `auto_tagger.py` | LLM-powered auto-tagging engine (few-shot from `examples.json`) |
| `tagger_flask.py` | Flask web dashboard (port 5050) |
| `tagger_cli.py` | Terminal-based interactive tagger |
| `review_emails.py` | Terminal email review helper |
| `suggest.py` | Lightweight label suggestion helper |
| `templates/dashboard.html` | Dashboard HTML template |
| `static/styles.css` | Dashboard styles |

### Data Files (not committed)

| File | Purpose |
|---|---|
| `token.json` | OAuth2 refresh token (auto-generated) |
| `examples.json` | Your training data — past decisions the LLM learns from |
| `pending_suggestions.json` | Cached LLM suggestions (survives page refresh) |

## Web Dashboard Features

- **Review table** with columns: #, From, Subject, Snippet, Suggestion, Reasoning, Actions, Options, Status
- **Per-row actions**: Accept (✓), Delete (🗑), Pick Tags (🏷), Skip (→)
- **"Mark as Read" checkbox** — removes the UNREAD label on commit
- **"Delete Later" checkbox** — keeps email unread after tagging (mutual exclusive with delete)
- **Tag picker modal** with search/filter, frequency-ordered labels, and sticky multi-select
- **"Accept All Pending"** — bulk-accept all rows with LLM suggestions
- **"Hide Already-Processed"** — toggle to hide rows already in `examples.json`
- **Background batch fetching** — emails load in batches; review the first while the rest load
- **Loading bar** with progress, spinner, and last-activity timestamp
- **Post-commit LLM summaries** — body summaries generated after commit (when LLM available)

## Auto-Tagging Engine

The engine in `auto_tagger.py` uses two strategies:

1. **LLM path** — sends the email + similar past examples to a local LLM (llama.cpp) via HTTP. The LLM reasons about which tags apply and returns a JSON response with labels and reasoning.

2. **Rule-based fallback** — scores each label independently by sender/subject/body similarity against `examples.json`. Labels within a threshold of the top score are returned. Delete only wins when it outscores all tags combined.

The LLM URL defaults to `http://localhost:11434/v1/messages` and can be overridden with `AUTO_TAGGER_LLM_URL`.

## Configuration

| Environment Variable | Default | Purpose |
|---|---|---|
| `AUTO_TAGGER_LLM_URL` | `http://localhost:11434/v1/messages` | LLM API endpoint |
| `AUTO_TAGGER_EXAMPLES` | `examples.json` | Training data path |
| `AUTO_TAGGER_SKIP_AUTH` | — | Skip auth check in CLI (for testing) |
| `AUTO_TAGGER_SKIP_LABELS` | — | Skip label fetch in CLI (for testing) |

## Gmail Scopes

- `gmail.readonly` — read emails and labels
- `gmail.modify` — apply labels, delete (trash), mark as read

## Security

- `token.json`, `credentials.json`, `examples.json`, and `pending_suggestions.json` are all `.gitignore`d
- Never commit credential or token files
- OAuth tokens stay local; the LLM runs locally by default

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
