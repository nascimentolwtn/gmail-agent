#!/usr/bin/env python3
# tagger_flask.py — Flask web interface for Gmail auto-tagger with background loading

"""
Web UI for reviewing and committing auto-tag suggestions.
Emails are fetched in small batches so the user can start reviewing
the first batch while the rest load in the background.

Routes:
  GET  /              — Dashboard (first batch rendered immediately)
  GET  /api/status    — JSON: {done, loaded, total} progress info
  GET  /api/more      — JSON: next batch of emails+decisions for the frontend
  GET  /api/labels    — JSON: available Gmail labels
  POST /api/commit    — JSON: apply confirmed decisions to Gmail API

Run:  python tagger_flask.py
Open: http://localhost:5050
"""

from __future__ import annotations

import json
import threading
from typing import Optional

from flask import Flask, request, jsonify, render_template_string

from auth_test import get_gmail_service
from fetch_emails import get_unread_emails_paginated
from auto_tagger import auto_tag_email, load_examples
from review_emails import load_labels, save_examples

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Shared background-fetch state (protected by a lock)
# ---------------------------------------------------------------------------
_fetch_lock = threading.Lock()
_fetch_state: dict = {
    "done": False,
    "total": 0,               # Gmail's resultSizeEstimate
    "loaded": 0,              # how many emails we've fetched + tagged so far
    "batches": [],            # list of (email_dict_list, decision_dict_list) tuples
    "error": None,
    "last_served_idx": 0,     # index into batches for /api/more cursor
}

BATCH_SIZE = 20              # emails per background batch


def _reset_fetch_state() -> None:
    """Clear shared state before a new fetch cycle."""
    with _fetch_lock:
        _fetch_state.update({
            "done": False,
            "total": 0,
            "loaded": 0,
            "batches": [],
            "error": None,
            "last_served_idx": 0,
        })


def _background_fetch(service, examples: list, label_map: dict, total_expected: int) -> None:
    """Fetch remaining batches in a background thread.

    The first batch is already done by the time this starts, so we
    continue from page_token returned by the paginated fetcher.
    """
    page_token: Optional[str] = None
    first_batch_done = True  # the dashboard route already did batch 0

    try:
        while True:
            emails, _, total, next_token = get_unread_emails_paginated(
                service,
                page_token=page_token,
                batch_size=BATCH_SIZE,
            )

            if not emails and not first_batch_done:
                break

            # Tag each email
            decisions = []
            for email in emails:
                msg_for_tagging = {**email, "snippet": email.get("body_snippet", "")}
                decision = auto_tag_email(msg_for_tagging, examples, label_map)
                decisions.append({
                    "action": decision.action,
                    "reasoning": decision.reasoning,
                })

            with _fetch_lock:
                _fetch_state["batches"].append((
                    [{
                        "id": e["id"],
                        "from": e["from"],
                        "subject": e["subject"],
                        "body_snippet": e.get("body_snippet", "")[:150],
                    } for e in emails],
                    decisions,
                ))
                _fetch_state["loaded"] += len(emails)
                if total_expected == 0:
                    _fetch_state["total"] = total

            if not next_token:
                break
            page_token = next_token
            first_batch_done = False

    except Exception as exc:
        with _fetch_lock:
            _fetch_state["error"] = str(exc)
    finally:
        with _fetch_lock:
            _fetch_state["done"] = True


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gmail Auto-Tagger</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #f5f5f5; color: #333; padding: 20px; }
    h1 { margin-bottom: 4px; font-size: 1.5rem; }
    .subtitle { color: #666; margin-bottom: 20px; font-size: 0.9rem; }
    .toolbar { margin-bottom: 16px; display: flex; gap: 10px; align-items: center; }
    .toolbar button { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer;
                      font-size: 0.9rem; font-weight: 600; }
    .btn-commit { background: #1a73e8; color: #fff; }
    .btn-commit:hover { background: #1557b0; }
    .btn-commit:disabled { background: #ccc; cursor: not-allowed; }
    .btn-refresh { background: #fff; color: #333; border: 1px solid #ddd; }
    .btn-refresh:hover { background: #f0f0f0; }
    .stats { font-size: 0.85rem; color: #666; }
    .loading-bar { margin-bottom: 12px; padding: 8px 14px; background: #e8f0fe;
                   border-radius: 6px; font-size: 0.85rem; color: #1a73e8;
                   display: flex; align-items: center; gap: 8px; }
    .loading-bar.done { background: #e6f4ea; color: #34a853; }
    .loading-bar.error { background: #fce8e6; color: #c5221f; }
    .spinner { width: 14px; height: 14px; border: 2px solid #1a73e8; border-top-color: transparent;
               border-radius: 50%; animation: spin 0.8s linear infinite; }
    .loading-bar.done .spinner { display: none; }
    @keyframes spin { to { transform: rotate(360deg); } }
    table { width: 100%; border-collapse: collapse; background: #fff;
            border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    th { background: #1a73e8; color: #fff; padding: 10px 12px; text-align: left;
         font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; }
    td { padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 0.85rem;
         vertical-align: top; }
    tr:hover { background: #f8f9fa; }
    tr.skipped { opacity: 0.45; }
    tr.committed { background: #e8f5e9; }
    .from { max-width: 180px; white-space: nowrap; overflow: hidden;
            text-overflow: ellipsis; }
    .subject { max-width: 240px; white-space: nowrap; overflow: hidden;
               text-overflow: ellipsis; }
    .snippet { max-width: 200px; color: #666; font-size: 0.8rem;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .reasoning { max-width: 200px; color: #888; font-size: 0.75rem;
                 font-style: italic; white-space: nowrap; overflow: hidden;
                 text-overflow: ellipsis; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
             font-size: 0.75rem; font-weight: 600; }
    .badge-delete { background: #fce8e6; color: #c5221f; }
    .badge-tag { background: #e8f0fe; color: #1a73e8; }
    .badge-none { background: #f1f3f4; color: #888; }
    .actions button { padding: 4px 10px; margin: 2px; border: 1px solid #ddd;
                      border-radius: 4px; cursor: pointer; font-size: 0.75rem;
                      background: #fff; }
    .actions button:hover { background: #f0f0f0; }
    .actions .btn-accept { border-color: #34a853; color: #34a853; }
    .actions .btn-accept:hover { background: #e6f4ea; }
    .actions .btn-delete { border-color: #ea4335; color: #ea4335; }
    .actions .btn-delete:hover { background: #fce8e6; }
    .actions .btn-pick   { border-color: #1a73e8; color: #1a73e8; }
    .actions .btn-pick:hover { background: #e8f0fe; }
    .actions .btn-skip   { border-color: #aaa; color: #aaa; }
    .actions .btn-skip:hover { background: #f1f3f4; }
    .status { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .status-pending   { color: #888; }
    .status-accepted  { color: #34a853; }
    .status-delete    { color: #ea4335; }
    .status-skipped   { color: #aaa; }
    .status-committed { color: #1a73e8; }
    /* Tag picker modal */
    .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                     background: rgba(0,0,0,0.4); z-index: 100; justify-content: center;
                     align-items: center; }
    .modal-overlay.active { display: flex; }
    .modal { background: #fff; border-radius: 10px; padding: 24px; max-width: 420px;
             width: 90%; max-height: 70vh; overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.2); }
    .modal h3 { margin-bottom: 12px; font-size: 1rem; }
    .modal select { width: 100%; min-height: 160px; border: 1px solid #ddd; border-radius: 6px;
                    padding: 8px; font-size: 0.85rem; margin-bottom: 12px; }
    .modal .modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .modal .modal-actions button { padding: 6px 16px; border-radius: 4px; border: 1px solid #ddd;
                                   cursor: pointer; font-size: 0.85rem; }
    .modal .btn-confirm { background: #1a73e8; color: #fff; border-color: #1a73e8; }
    .modal .btn-confirm:hover { background: #1557b0; }
    .modal .btn-cancel { background: #fff; }
    .modal .btn-cancel:hover { background: #f0f0f0; }
    /* Toast */
    .toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px;
             border-radius: 6px; color: #fff; font-size: 0.85rem; z-index: 200;
             display: none; }
    .toast.show { display: block; }
    .toast-success { background: #34a853; }
    .toast-error   { background: #ea4335; }
  </style>
</head>
<body>

<h1>📬 Gmail Auto-Tagger</h1>
<p class="subtitle">Review auto-suggested tags, adjust, then commit to your Gmail account.</p>

<!-- Loading / progress bar -->
<div class="loading-bar" id="loadingBar">
  <div class="spinner" id="spinner"></div>
  <span id="loadingText">Loading emails…</span>
</div>

<div class="toolbar">
  <button class="btn-commit" id="btnCommit" onclick="commitAll()" disabled>
    ✓ Commit All
  </button>
  <button class="btn-refresh" onclick="location.reload()">↻ Refresh</button>
  <span class="stats" id="stats"></span>
</div>

<table>
  <thead>
    <tr>
      <th>#</th>
      <th>From</th>
      <th>Subject</th>
      <th>Snippet</th>
      <th>Suggestion</th>
      <th>Reasoning</th>
      <th>Actions</th>
      <th>Status</th>
    </tr>
  </thead>
  <tbody id="emailTable">
    <!-- rows injected by JS -->
  </tbody>
</table>

<!-- Tag picker modal -->
<div class="modal-overlay" id="tagModal">
  <div class="modal">
    <h3>🏷 Pick Tags</h3>
    <select id="tagSelect" multiple></select>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeTagModal()">Cancel</button>
      <button class="btn-confirm" onclick="confirmTagPick()">Confirm</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
// ── Data injected by server (first batch only) ───────────────────────────
const INITIAL_EMAILS = {{ emails_json | safe }};
const LABELS = {{ labels_json | safe }};

// ── State ────────────────────────────────────────────────────────────────
// Each row: { status: 'pending'|'accepted'|'delete'|'tagged'|'skipped'|'committed',
//             action: null|'delete'|['tag:LABEL',...] }
const EMAILS = [];      // { id, from, subject, body_snippet }
const DECISIONS = [];   // { action, reasoning }
const state = [];       // per-row UI state

// ── Helpers ──────────────────────────────────────────────────────────────
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function formatSuggestionBadge(action) {
  if (!action) return '<span class="badge badge-none">—</span>';
  if (action === 'delete') return '<span class="badge badge-delete">🗑 delete</span>';
  if (Array.isArray(action)) {
    const labels = action.map(a => a.replace('tag:', '')).join(', ');
    return `<span class="badge badge-tag">🏷 ${escHtml(labels)}</span>`;
  }
  return `<span class="badge badge-tag">🏷 ${escHtml(action)}</span>`;
}

function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show toast-' + type;
  setTimeout(() => { t.className = 'toast'; }, 4000);
}

// ── Build a table row for one email ──────────────────────────────────────
function buildRow(idx) {
  const email = EMAILS[idx];
  const decision = DECISIONS[idx];
  const tr = document.createElement('tr');
  tr.id = 'row-' + idx;

  const suggestionBadge = formatSuggestionBadge(decision.action);
  const reasoning = (decision.reasoning || '').substring(0, 120);

  tr.innerHTML = `
    <td>${idx + 1}</td>
    <td class="from" title="${escHtml(email.from)}">${escHtml(email.from)}</td>
    <td class="subject" title="${escHtml(email.subject)}">${escHtml(email.subject)}</td>
    <td class="snippet" title="${escHtml(email.body_snippet)}">${escHtml(email.body_snippet || '')}</td>
    <td>${suggestionBadge}</td>
    <td class="reasoning" title="${escHtml(decision.reasoning || '')}">${escHtml(reasoning)}</td>
    <td class="actions">
      <button class="btn-accept" onclick="acceptRow(${idx})">✓</button>
      <button class="btn-delete" onclick="deleteRow(${idx})">🗑</button>
      <button class="btn-pick"   onclick="openTagModal(${idx})">🏷</button>
      <button class="btn-skip"   onclick="skipRow(${idx})">→</button>
    </td>
    <td class="status status-pending" id="status-${idx}">pending</td>
  `;
  return tr;
}

// ── Add a batch of emails to the table ───────────────────────────────────
function addBatch(emails, decisions) {
  const tbody = document.getElementById('emailTable');
  const startIdx = EMAILS.length;

  emails.forEach((email, i) => {
    const idx = startIdx + i;
    EMAILS.push(email);
    DECISIONS.push(decisions[i]);
    const hasSuggestion = decisions[i].action !== null && decisions[i].action !== '';
    state.push({
      status: hasSuggestion ? 'pending' : 'skipped',
      action: hasSuggestion ? decisions[i].action : null,
    });
    tbody.appendChild(buildRow(idx));
  });

  updateStats();
}

// ── Row actions ──────────────────────────────────────────────────────────
function acceptRow(idx) {
  state[idx] = { status: 'accepted', action: DECISIONS[idx].action };
  updateRowUI(idx);
}

function deleteRow(idx) {
  state[idx] = { status: 'delete', action: 'delete' };
  updateRowUI(idx);
}

function skipRow(idx) {
  state[idx] = { status: 'skipped', action: null };
  updateRowUI(idx);
}

function updateRowUI(idx) {
  const row = document.getElementById('row-' + idx);
  const s = state[idx];
  row.className = s.status === 'skipped' ? 'skipped' : '';
  const statusTd = document.getElementById('status-' + idx);
  statusTd.textContent = s.status;
  statusTd.className = 'status status-' + s.status;
  updateStats();
}

// ── Tag picker modal ────────────────────────────────────────────────────
let modalRowIdx = null;

function openTagModal(idx) {
  modalRowIdx = idx;
  const sel = document.getElementById('tagSelect');
  sel.innerHTML = '';
  LABELS.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l.name;
    opt.textContent = l.name;
    sel.appendChild(opt);
  });
  document.getElementById('tagModal').classList.add('active');
}

function closeTagModal() {
  document.getElementById('tagModal').classList.remove('active');
  modalRowIdx = null;
}

function confirmTagPick() {
  const sel = document.getElementById('tagSelect');
  const selected = Array.from(sel.selectedOptions).map(o => o.value);
  if (selected.length > 0 && modalRowIdx !== null) {
    state[modalRowIdx] = {
      status: 'tagged',
      action: selected.map(l => 'tag:' + l),
    };
    updateRowUI(modalRowIdx);
  }
  closeTagModal();
}

// ── Commit ───────────────────────────────────────────────────────────────
async function commitAll() {
  const decisions = [];
  state.forEach((s, idx) => {
    if (s.status === 'accepted' || s.status === 'delete' || s.status === 'tagged') {
      if (s.action) {
        decisions.push({
          email_id: EMAILS[idx].id,
          action: s.action,
        });
      }
    }
  });

  if (decisions.length === 0) {
    showToast('No decisions to commit.', 'error');
    return;
  }

  const btn = document.getElementById('btnCommit');
  btn.disabled = true;
  btn.textContent = 'Committing...';

  try {
    const resp = await fetch('/api/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisions }),
    });
    const data = await resp.json();

    // Mark committed rows
    state.forEach((s, idx) => {
      if (s.status === 'accepted' || s.status === 'delete' || s.status === 'tagged') {
        if (s.action) {
          state[idx].status = 'committed';
          const row = document.getElementById('row-' + idx);
          if (row) row.className = 'committed';
          const st = document.getElementById('status-' + idx);
          if (st) { st.textContent = 'committed'; st.className = 'status status-committed'; }
        }
      }
    });

    showToast(`✓ Committed: ${data.tagged} tagged, ${data.deleted} deleted, ${data.errors} errors`, 'success');
  } catch (err) {
    showToast('Commit failed: ' + err, 'error');
  } finally {
    btn.textContent = '✓ Commit All';
    updateStats();
  }
}

// ── Stats ────────────────────────────────────────────────────────────────
function updateStats() {
  const total = state.length;
  const pending = state.filter(s =>
    s.status === 'pending' || s.status === 'accepted' || s.status === 'delete' || s.status === 'tagged'
  ).length;
  const skipped = state.filter(s => s.status === 'skipped').length;
  const committed = state.filter(s => s.status === 'committed').length;
  document.getElementById('stats').textContent =
    `${total} emails loaded | ${pending} ready | ${skipped} skipped | ${committed} committed`;
  document.getElementById('btnCommit').disabled = pending === 0;
}

// ── Background polling ──────────────────────────────────────────────────
let pollTimer = null;

function startPolling() {
  pollTimer = setInterval(pollForMore, 2000);
}

async function pollForMore() {
  try {
    const resp = await fetch('/api/more');
    const data = await resp.json();

    if (data.emails && data.emails.length > 0) {
      addBatch(data.emails, data.decisions);
    }

    updateLoadingBar(data.loaded, data.total, data.done, data.error);

    if (data.done) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  } catch (err) {
    // transient network error — keep polling
    console.warn('poll error:', err);
  }
}

function updateLoadingBar(loaded, total, done, error) {
  const bar = document.getElementById('loadingBar');
  const text = document.getElementById('loadingText');

  if (error) {
    bar.className = 'loading-bar error';
    text.textContent = '⚠ Error loading emails: ' + error;
    return;
  }

  if (done) {
    bar.className = 'loading-bar done';
    text.textContent = `✓ All ${loaded} emails loaded`;
  } else {
    bar.className = 'loading-bar';
    const totalStr = total > 0 ? ` / ~${total}` : '';
    text.textContent = `⏳ Loading emails… ${loaded}${totalStr} loaded so far — review while you wait!`;
  }
}

// ── Init ─────────────────────────────────────────────────────────────────
function init() {
  // Populate initial batch
  addBatch(
    INITIAL_EMAILS.map(e => e.email),
    INITIAL_EMAILS.map(e => e.decision),
  );

  // Populate label picker
  // (LABELS already available from server template)

  // Show initial loading state
  updateLoadingBar(INITIAL_EMAILS.length, {{ total_json | safe }}, false, null);

  // Start polling for background batches
  startPolling();
}

init();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    """Render the main dashboard with the first batch of emails.

    Fetches the first batch synchronously so the page has data immediately,
    then kicks off a background thread to fetch the rest.
    """
    service = get_gmail_service()
    examples = load_examples("examples.json")
    label_map = load_labels(service)

    # Reset shared state
    _reset_fetch_state()

    # Fetch first batch synchronously (fast — only BATCH_SIZE emails)
    first_batch, _, total, next_token = get_unread_emails_paginated(
        service, page_token=None, batch_size=BATCH_SIZE
    )

    # Tag the first batch
    first_emails_data = []
    for email in first_batch:
        msg_for_tagging = {**email, "snippet": email.get("body_snippet", "")}
        decision = auto_tag_email(msg_for_tagging, examples, label_map)
        first_emails_data.append({
            "email": {
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "body_snippet": email.get("body_snippet", "")[:150],
            },
            "decision": {
                "action": decision.action,
                "reasoning": decision.reasoning,
            },
        })

    # Store first batch in shared state
    with _fetch_lock:
        _fetch_state["total"] = total
        _fetch_state["loaded"] = len(first_batch)
        _fetch_state["batches"].append((
            [{
                "id": e["id"],
                "from": e["from"],
                "subject": e["subject"],
                "body_snippet": e.get("body_snippet", "")[:150],
            } for e in first_batch],
            [{"action": d["decision"]["action"], "reasoning": d["decision"]["reasoning"]}
             for d in first_emails_data],
        ))

    # Kick off background thread for remaining batches
    if next_token:
        t = threading.Thread(
            target=_background_fetch,
            args=(service, examples, label_map, total),
            daemon=True,
        )
        t.start()

    # Labels for the tag picker
    label_list = [{"name": k, "id": v} for k, v in label_map.items()]

    return render_template_string(
        DASHBOARD_HTML,
        emails_json=json.dumps(first_emails_data, ensure_ascii=False),
        labels_json=json.dumps(label_list, ensure_ascii=False),
        total_json=json.dumps(total),
    )


@app.route("/api/status")
def api_status():
    """Return current loading progress."""
    with _fetch_lock:
        return jsonify({
            "done": _fetch_state["done"],
            "loaded": _fetch_state["loaded"],
            "total": _fetch_state["total"],
            "error": _fetch_state["error"],
        })


@app.route("/api/more")
def api_more():
    """Return the next batch of emails+decisions that the client hasn't seen yet.

    The client polls this endpoint; each call returns whatever new batches
    have been fetched since the last call.
    """
    with _fetch_lock:
        batches = _fetch_state["batches"]
        last_idx = _fetch_state["last_served_idx"]

        if last_idx >= len(batches):
            # No new batches since last poll
            return jsonify({
                "emails": [],
                "decisions": [],
                "loaded": _fetch_state["loaded"],
                "total": _fetch_state["total"],
                "done": _fetch_state["done"],
                "error": _fetch_state["error"],
            })

        # Flatten all unseen batches into one response
        all_emails = []
        all_decisions = []
        for email_list, decision_list in batches[last_idx:]:
            all_emails.extend(email_list)
            all_decisions.extend(decision_list)

        _fetch_state["last_served_idx"] = len(batches)

        return jsonify({
            "emails": all_emails,
            "decisions": all_decisions,
            "loaded": _fetch_state["loaded"],
            "total": _fetch_state["total"],
            "done": _fetch_state["done"],
            "error": _fetch_state["error"],
        })


@app.route("/api/labels")
def api_labels():
    """Return available Gmail labels as JSON."""
    service = get_gmail_service()
    label_map = load_labels(service)
    return jsonify({"labels": [{"name": k, "id": v} for k, v in label_map.items()]})


@app.route("/api/commit", methods=["POST"])
def api_commit():
    """Apply confirmed decisions to Gmail API.

    Expected JSON body:
      {"decisions": [{"email_id": "...", "action": "delete" | ["tag:LABEL1", ...]}]}

    Returns:
      {"tagged": N, "deleted": N, "errors": N, "details": [...]}
    """
    body = request.get_json(force=True)
    raw_decisions = body.get("decisions", [])

    if not raw_decisions:
        return jsonify({"error": "no decisions provided"}), 400

    service = get_gmail_service()
    label_map = load_labels(service)

    tagged = 0
    deleted = 0
    errors = 0
    details: list[dict] = []

    for entry in raw_decisions:
        email_id = entry.get("email_id", "")
        action = entry.get("action")

        if not email_id or not action:
            errors += 1
            details.append({"email_id": email_id, "error": "missing email_id or action"})
            continue

        try:
            if action == "delete":
                service.users().messages().trash(userId="me", id=email_id).execute()
                deleted += 1
                details.append({"email_id": email_id, "result": "trashed"})

            elif isinstance(action, list):
                label_ids = []
                for a in action:
                    label_name = a[4:] if a.startswith("tag:") else a
                    lid = label_map.get(label_name)
                    if lid:
                        label_ids.append(lid)

                if label_ids:
                    service.users().messages().modify(
                        userId="me",
                        id=email_id,
                        body={"addLabelIds": label_ids},
                    ).execute()
                    tagged += 1
                    details.append({"email_id": email_id, "result": "tagged", "labels": label_ids})
                else:
                    errors += 1
                    details.append({"email_id": email_id, "error": "no valid label ids"})

            else:
                errors += 1
                details.append({"email_id": email_id, "error": "unrecognised action: " + str(action)})

        except Exception as exc:
            errors += 1
            details.append({"email_id": email_id, "error": str(exc)})

    # Save committed decisions to examples.json
    if tagged + deleted > 0:
        try:
            examples = load_examples("examples.json")
            for entry in raw_decisions:
                email_id = entry.get("email_id", "")
                action = entry.get("action")
                if not email_id or not action:
                    continue
                examples.append({
                    "from": "(web)",
                    "subject": "(web)",
                    "snippet": "",
                    "action": action,
                })
            save_examples(examples)
        except Exception:
            pass  # don't fail the commit if saving examples fails

    return jsonify({
        "tagged": tagged,
        "deleted": deleted,
        "errors": errors,
        "details": details,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5050)
