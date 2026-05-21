#!/usr/bin/env python3
# tagger_flask.py — Flask web interface for Gmail auto-tagging

"""
Web UI for reviewing and committing auto-tag suggestions.

Routes:
  GET  /              — Dashboard (unread emails + suggestions)
  GET  /api/labels    — JSON: available Gmail labels
  POST /api/suggest   — JSON: auto-tag suggestions for all unread emails
  POST /api/commit    — JSON: apply confirmed decisions to Gmail API

Run:  python tagger_flask.py
Open: http://localhost:5050
"""

from __future__ import annotations

import json
import os
from typing import Optional

from flask import Flask, request, jsonify, render_template_string

from auth_test import get_gmail_service
from fetch_emails import get_unread_emails
from auto_tagger import auto_tag_email, load_examples, EmailDecision
from review_emails import load_labels, save_examples

app = Flask(__name__)

# ---------------------------------------------------------------------------
# HTML template (inline — no template directory needed)
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
// ── Data injected by server ──────────────────────────────────────────────
const EMAILS = {{ emails_json | safe }};
const LABELS = {{ labels_json | safe }};

// ── State ────────────────────────────────────────────────────────────────
// Each row: { status: 'pending'|'accepted'|'delete'|'tagged'|'skipped'|'committed',
//             action: null|'delete'|['tag:LABEL',...] }
const state = [];

// ── Init ─────────────────────────────────────────────────────────────────
function init() {
  const tbody = document.getElementById('emailTable');
  tbody.innerHTML = '';

  EMAILS.forEach((item, idx) => {
    const email = item.email;
    const decision = item.decision;
    // Default state from server suggestion
    const hasSuggestion = decision.action !== null && decision.action !== '';
    state[idx] = {
      status: hasSuggestion ? 'pending' : 'skipped',
      action: hasSuggestion ? decision.action : null,
    };

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
    tbody.appendChild(tr);
  });

  updateStats();
}

// ── Row actions ──────────────────────────────────────────────────────────
function acceptRow(idx) {
  state[idx] = { status: 'accepted', action: EMAILS[idx].decision.action };
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
          email_id: EMAILS[idx].email.id,
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

// ── Helpers ──────────────────────────────────────────────────────────────
function formatSuggestionBadge(action) {
  if (!action) return '<span class="badge badge-none">—</span>';
  if (action === 'delete') return '<span class="badge badge-delete">🗑 delete</span>';
  if (Array.isArray(action)) {
    const labels = action.map(a => a.replace('tag:', '')).join(', ');
    return `<span class="badge badge-tag">🏷 ${escHtml(labels)}</span>`;
  }
  return `<span class="badge badge-tag">🏷 ${escHtml(action)}</span>`;
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function updateStats() {
  const total = state.length;
  const pending = state.filter(s => s.status === 'pending' || s.status === 'accepted' || s.status === 'delete' || s.status === 'tagged').length;
  const skipped = state.filter(s => s.status === 'skipped').length;
  const committed = state.filter(s => s.status === 'committed').length;
  document.getElementById('stats').textContent =
    `${total} emails | ${pending} ready | ${skipped} skipped | ${committed} committed`;
  document.getElementById('btnCommit').disabled = pending === 0;
}

function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show toast-' + type;
  setTimeout(() => { t.className = 'toast'; }, 4000);
}

// Start
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
    """Render the main dashboard with unread emails and suggestions."""
    service = get_gmail_service()
    examples = load_examples("examples.json")
    label_map = load_labels(service)
    emails, unreadable, total = get_unread_emails(service, max_results=50)

    # Build email+decision data for the template
    emails_data = []
    for email in emails:
        msg_for_tagging = {**email, "snippet": email.get("body_snippet", "")}
        decision = auto_tag_email(msg_for_tagging, examples, label_map)
        emails_data.append({
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

    # Labels for the tag picker
    label_list = [{"name": k, "id": v} for k, v in label_map.items()]

    return render_template_string(
        DASHBOARD_HTML,
        emails_json=json.dumps(emails_data, ensure_ascii=False),
        labels_json=json.dumps(label_list, ensure_ascii=False),
    )


@app.route("/api/labels")
def api_labels():
    """Return available Gmail labels as JSON."""
    service = get_gmail_service()
    label_map = load_labels(service)
    return jsonify({"labels": [{"name": k, "id": v} for k, v in label_map.items()]})


@app.route("/api/suggest", methods=["POST"])
def api_suggest():
    """Return auto-tag suggestions for all unread emails (JSON)."""
    service = get_gmail_service()
    examples = load_examples("examples.json")
    label_map = load_labels(service)
    emails, unreadable, total = get_unread_emails(service, max_results=50)

    results = []
    for email in emails:
        msg_for_tagging = {**email, "snippet": email.get("body_snippet", "")}
        decision = auto_tag_email(msg_for_tagging, examples, label_map)
        results.append({
            "email": {
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "body_snippet": email.get("body_snippet", "")[:150],
            },
            "suggestion": {
                "action": decision.action,
                "reasoning": decision.reasoning,
            },
        })

    return jsonify({"emails": results, "total": total, "unreadable": unreadable})


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
                # We don't have full email metadata here, store what we can
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
