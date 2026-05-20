# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Run the Gmail API client
```bash
python auth_test.py
```
Fetches OAuth tokens via browser and saves `token.json` for subsequent runs.

### Authenticate fresh (new token or no existing session)
```bash
rm -f token.json && python auth_test.py
```

### Single file debugging
Directly edit [auth_test.py](file:///home/lw_na/git/gmail-agent/auth_test.py); the code has minimal branching so full re-read is unnecessary for small changes.

## Architecture & Structure

This project uses a **monolithic service pattern** — all Gmail API logic lives in one module ([auth_test.py:13-25](file:///home/lw_na/git/gmail-agent/auth_test.py#L13-L25)). There are no architectural decisions to track across multiple files; the entire authentication flow is self-contained and testable via unit testing individual functions (e.g., `get_gmail_service()`).

## Project Notes & Guidelines

### OAuth Token Management
- **`token.json`** caches per-user refresh tokens — each authenticated user gets their own file under `.gitignore`. Never commit this.
- Tokens persist across sessions; removing the file forces a full OAuth re-authentication flow (open browser dialog, grant scopes).
- Scopes: `gmail.readonly` + `gmail.modify` (read emails, apply labels/tags, delete)

### Google OAuth Credentials Files
Both [credentials.json](file:///home/lw_na/git/gmail-agent/credentials.json) and [`client_secret_*.json`](file:///home/lw_na/git/gmail-agent/client_secret_64767593908-fh73f9k5ue98epeta0u2ro2m8mjmkoq5.apps.googleusercontent.com.json) are **service account keys** issued by the Google Cloud Console. These files contain secrets that should never be committed to git or shared publicly.

### Development Workflow
1. Edit [auth_test.py](file:///home/lw_na/git/gmail-agent/auth_test.py) — the entire Gmail API logic is contained in a single module with minimal branching, so full file re-read isn't necessary for small changes
2. Run `python auth_test.py` to authenticate and test the flow
3. For integration testing, use [fetch_gmail_labels.py](file:///home/lw_na/git/gmail-agent/fetch_gmail_labels.py) as a reference implementation

### Key Dependencies
- **google-api-python-client**: Official Gmail API Python client
- **google-auth-oauthlib**: OAuth 2.0 authorization flow helpers
- **google-auth-httplib2**: HTTP transport for authentication

### Claude Code with OpenRounter API - Test Results:
  "model": "nvidia/nemotron-3-nano-30b-a3b:free",        only diff
  "model": "nvidia/nemotron-3-super-120b-a12b:free",     slow
  "model": "deepseek/deepseek-v4-flash:free",            retries
  "model": "qwen/qwen3-next-80b-a3b-instruct:free",      retries
  "model": "openai/gpt-oss-20b:free",                    retries
  "model": "qwen/qwen3-coder:free",                      retries
  "model": "meta-llama/llama-3.3-70b-instruct:free",     retries
  "model": "openrouter/owl-alpha",                       working, sometimes slow
   