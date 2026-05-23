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
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, request, jsonify, render_template

from auth_test import get_gmail_service
from fetch_emails import get_unread_emails_paginated
from auto_tagger import auto_tag_email, load_examples, summarize_email_bodies
from review_emails import load_labels, save_examples, ordered_labels_for_picker

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
    "last_activity": None,    # {action: str, ts: ISO-8601 UTC string}
    "background_fetch_started": False,
    "next_page_token": None,   # stored so /api/fetch_next can resume
    "fetching": False,         # True while a fetch HTTP request is in flight
    "all_fetched": False,      # true when no more pages
}

BATCH_SIZE = 20              # emails per background batch
PENDING_SUGGESTIONS_FILE = "pending_suggestions.json"


def _load_pending_suggestions() -> dict:
    """Load cached LLM suggestions for pending emails. Returns {email_id: {action, reasoning}}."""
    if not os.path.exists(PENDING_SUGGESTIONS_FILE):
        return {}
    try:
        with open(PENDING_SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_pending_suggestions(suggestions: dict) -> None:
    """Persist cached LLM suggestions to disk."""
    with open(PENDING_SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, indent=2, ensure_ascii=False)


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
            "last_activity": None,
            "background_fetch_started": False,
            "next_page_token": None,
            "all_fetched": False,
        })


def _background_fetch(service, examples: list, label_map: dict, total_expected: int, start_page_token: Optional[str] = None) -> None:
    """Fetch remaining batches in a background thread.

    The first batch is already done by the time this starts, so we
    continue from the page_token returned by the paginated fetcher (batch 0).
    """
    page_token: Optional[str] = start_page_token
    first_batch_done = start_page_token is not None  # skip empty first iteration when resuming mid-list

    try:
        while True:
            emails, _, total, next_token = get_unread_emails_paginated(
                service,
                page_token=page_token,
                batch_size=BATCH_SIZE,
            )

            if not emails:
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
            _fetch_state["last_activity"] = {
                "action": "fetch_complete",
                "ts": datetime.now(timezone.utc).isoformat(),
            }


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

    # Store first batch in shared state (index 0 — already rendered in page HTML)
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
        # Skip batch 0 when serving /api/more — client already has it from INITIAL_EMAILS
        _fetch_state["last_served_idx"] = 1

    # Record first-batch fetch timestamp
    with _fetch_lock:
        _fetch_state["last_activity"] = {
            "action": "first_batch",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    # Store next_token so /api/fetch_next can load more on user demand.
    # Do NOT auto-start background fetch — user controls via dashboard button.
    with _fetch_lock:
        _fetch_state["next_page_token"] = next_token
        _fetch_state["all_fetched"] = next_token is None
        _fetch_state["done"] = next_token is None  # done if no more pages

    # Labels for the tag picker — top-N frequent first, then A–Z
    ordered_names = ordered_labels_for_picker(label_map, examples)
    label_list = [{"name": n, "id": label_map[n]} for n in ordered_names]
    # ordered_labels_for_picker returns top-N first, then A–Z — pass the count
    # so the JS can render a visual divider between the two sections.
    from review_emails import get_recent_labels
    top_n = len(get_recent_labels(examples, None))

    # Build lookup of already-processed emails from examples.json
    # so the UI can mark them without user intervention.
    already_ids: set[str] = set()
    already_keys: set[str] = set()  # "from||subject" composite
    for ex in examples:
        if ex.get("id"):
            already_ids.add(ex["id"])
        composite = f"{ex.get('from', '')}||{ex.get('subject', '')}"
        already_keys.add(composite)
    already_processed = {"ids": list(already_ids), "keys": list(already_keys)}

    return render_template(
        "dashboard.html",
        emails_json=json.dumps(first_emails_data, ensure_ascii=False),
        labels_json=json.dumps(label_list, ensure_ascii=False),
        total_json=json.dumps(total),
        already_processed_json=json.dumps(already_processed, ensure_ascii=False),
        top_n=top_n,
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
            "fetching": _fetch_state["fetching"],
            "last_activity": _fetch_state.get("last_activity"),
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
                "fetching": _fetch_state["fetching"],
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
            "fetching": _fetch_state["fetching"],
            "last_activity": _fetch_state.get("last_activity"),
        })


@app.route("/api/fetch_next", methods=["POST"])
def api_fetch_next():
    """Fetch the next batch of emails on user demand.

    Returns the new batch + updated progress.  If there are no more pages
    the response will be empty with done=true.
    """
    with _fetch_lock:
        _fetch_state["fetching"] = True
        page_token = _fetch_state.get("next_page_token")
        all_fetched = _fetch_state.get("all_fetched", False)

    try:
        if all_fetched or not page_token:
            with _fetch_lock:
                _fetch_state["done"] = True
            return jsonify({
                "emails": [], "decisions": [],
                "loaded": _fetch_state["loaded"],
                "total": _fetch_state["total"],
                "done": True,
                "all_fetched": True,
                "fetching": False,
            })

        service = get_gmail_service()
        examples = load_examples("examples.json")
        label_map = load_labels(service)

        emails, _, total, next_token = get_unread_emails_paginated(
            service, page_token=page_token, batch_size=BATCH_SIZE
        )

        # Tag each email and persist suggestions
        decisions = []
        pending_updates = {}
        for email in emails:
            msg_for_tagging = {**email, "snippet": email.get("body_snippet", "")}
            decision = auto_tag_email(msg_for_tagging, examples, label_map)
            decisions.append({
                "action": decision.action,
                "reasoning": decision.reasoning,
            })
            if decision.action:
                pending_updates[email["id"]] = {
                    "action": decision.action,
                    "reasoning": decision.reasoning,
                }

        # Merge into pending_suggestions.json
        if pending_updates:
            existing = _load_pending_suggestions()
            existing.update(pending_updates)
            _save_pending_suggestions(existing)

        with _fetch_lock:
            _fetch_state["batches"].append(([{
                "id": e["id"],
                "from": e["from"],
                "subject": e["subject"],
                "body_snippet": e.get("body_snippet", "")[:150],
            } for e in emails], decisions))
            _fetch_state["loaded"] += len(emails)
            _fetch_state["next_page_token"] = next_token
            _fetch_state["all_fetched"] = next_token is None
            _fetch_state["done"] = next_token is None
            _fetch_state["last_activity"] = {
                "action": "fetch_batch",
                "ts": datetime.now(timezone.utc).isoformat(),
            }

        return jsonify({
            "emails": [{
                "id": e["id"],
                "from": e["from"],
                "subject": e["subject"],
                "body_snippet": e.get("body_snippet", "")[:150],
            } for e in emails],
            "decisions": decisions,
            "loaded": _fetch_state["loaded"],
            "total": _fetch_state["total"],
            "done": _fetch_state["done"],
            "all_fetched": _fetch_state["all_fetched"],
            "last_activity": _fetch_state["last_activity"],
        })
    finally:
        with _fetch_lock:
            _fetch_state["fetching"] = False


@app.route("/api/suggestions")
def api_suggestions():
    """Return cached LLM suggestions for pending emails."""
    suggestions = _load_pending_suggestions()
    return jsonify({"suggestions": suggestions})


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
        mark_read = entry.get("mark_read", False)
        delete_later = entry.get("delete_later", False)

        if not email_id or not action:
            errors += 1
            details.append({"email_id": email_id, "error": "missing email_id or action"})
            continue

        try:
            if action == "delete" and not delete_later:
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

            elif delete_later:
                details.append({"email_id": email_id, "result": "delete_later"})

            else:
                errors += 1
                details.append({"email_id": email_id, "error": "unrecognised action: " + str(action)})

            if mark_read:
                service.users().messages().modify(
                    userId="me",
                    id=email_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()

        except Exception as exc:
            errors += 1
            details.append({"email_id": email_id, "error": str(exc)})

    # Save committed decisions to examples.json
    if tagged + deleted > 0 or any(e.get("delete_later") or e.get("mark_read") for e in raw_decisions):
        try:
            # Build email lookup from fetched batches
            with _fetch_lock:
                batches = list(_fetch_state.get("batches", []))
            email_lookup: dict[str, dict] = {}
            for email_list, _ in batches:
                for e in email_list:
                    email_lookup[e["id"]] = e

            examples = load_examples("examples.json")

            # Build set of already-processed keys to avoid duplicates
            seen_ids: set[str] = set()
            seen_keys: set[tuple[str, str]] = set()
            for ex in examples:
                if ex.get("id"):
                    seen_ids.add(ex["id"])
                else:
                    seen_keys.add((ex.get("from", ""), ex.get("subject", "")))

            for entry in raw_decisions:
                email_id = entry.get("email_id", "")
                action = entry.get("action")
                if not email_id or not action:
                    continue
                # Skip if already in examples (prefer id, fall back to from+subject)
                if email_id and email_id in seen_ids:
                    continue
                # Prefer client-provided fields; fall back to batch lookup
                em = email_lookup.get(email_id, {})
                from_val = entry.get("from") or em.get("from", "")
                subject_val = entry.get("subject") or em.get("subject", "")
                if (from_val, subject_val) in seen_keys:
                    continue
                new_entry = {
                    "id": email_id,
                    "from": from_val,
                    "subject": subject_val,
                    "snippet": entry.get("snippet") or em.get("body_snippet", ""),
                    "action": action,
                    "reasoning": entry.get("reasoning", ""),
                    "mark_read": entry.get("mark_read", False),
                    "delete_later": entry.get("delete_later", False),
                }
                examples.append(new_entry)
                # Track so subsequent entries in same batch also dedup
                if email_id:
                    seen_ids.add(email_id)
                seen_keys.add((from_val, subject_val))
            save_examples(examples)
        except Exception:
            pass  # don't fail the commit if saving examples fails

    # Generate post-commit LLM body summaries for non-deleted emails
    summaries: dict[str, str] = {}
    if tagged > 0:
        try:
            summary_inputs = []
            for entry in raw_decisions:
                email_id = entry.get("email_id", "")
                action = entry.get("action")
                if not email_id or action == "delete":
                    continue
                em = email_lookup.get(email_id, {})
                summary_inputs.append({
                    "id": email_id,
                    "from": entry.get("from") or em.get("from", ""),
                    "subject": entry.get("subject") or em.get("subject", ""),
                    "body_snippet": entry.get("snippet") or em.get("body_snippet", ""),
                })
            if summary_inputs:
                examples_for_summary = load_examples("examples.json")
                summaries = summarize_email_bodies(summary_inputs, examples_for_summary)
        except Exception:
            pass  # summaries are best-effort

    with _fetch_lock:
        _fetch_state["last_activity"] = {
            "action": "commit",
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    return jsonify({
        "tagged": tagged,
        "deleted": deleted,
        "errors": errors,
        "details": details,
        "last_activity": _fetch_state["last_activity"],
        "summaries": summaries,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5050)
