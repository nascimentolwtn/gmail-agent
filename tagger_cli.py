#!/usr/bin/env python3
# tagger_cli.py — Interactive CLI: auto-suggest tags, review, and commit to Gmail

"""
Workflow:
  1. Fetch unread emails
  2. Auto-tag each one (LLM + rule-based fallback)
  3. Show suggestion + LLM reasoning
  4. User accepts / overrides / skips
  5. Commit all decisions to Gmail API (apply labels / trash)
  6. Save decisions to examples.json
"""

from __future__ import annotations

import sys
from typing import Optional

from auth_test import get_gmail_service
from fetch_emails import get_unread_emails
from auto_tagger import auto_tag_email, load_examples, EmailDecision
from suggest import format_suggestion
from review_emails import load_labels, save_examples, pick_labels


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_email(email: dict, decision: EmailDecision, index: int, total: int) -> None:
    """Render a single email with its auto-tag suggestion and reasoning."""
    from_field = (email.get("from", "") or "")[:60]
    subject = (email.get("subject", "") or "")[:80]
    snippet = (email.get("body_snippet", "") or "")[:100].replace("\n", " ")

    if decision.action:
        if decision.is_delete:
            suggestion_str = "🗑  delete"
        elif isinstance(decision.action, list):
            labels = ", ".join(a.replace("tag:", "") for a in decision.action)
            suggestion_str = f"🏷  {labels}"
        else:
            suggestion_str = f"🏷  {decision.action}"
    else:
        suggestion_str = "— (no suggestion)"

    reason_lines: list[str] = []
    if decision.reasoning:
        for line in decision.reasoning.strip().split("\n"):
            reason_lines.append(line[:120])
            if len(reason_lines) >= 2:
                break
    reason_str = " | ".join(reason_lines) if reason_lines else ""

    print(f"\n{'─'*64}")
    print(f"  [{index}/{total}]  From:    {from_field}")
    print(f"             Subject: {subject}")
    print(f"             Snippet: {repr(snippet)}")
    print(f"             💡 Suggestion: {suggestion_str}")
    if reason_str:
        print(f"             📝 Reason: {reason_str}")


def get_user_action() -> str:
    """Prompt user for action. Returns: accept | delete | tag | skip | quit."""
    while True:
        raw = input("\n  Action [Enter=accept / d=delete / t=tag / s=skip / q=quit]: ").strip().lower()
        if raw == "":
            return "accept"
        if raw in ("d", "delete"):
            return "delete"
        if raw in ("t", "tag"):
            return "tag"
        if raw in ("s", "skip"):
            return "skip"
        if raw in ("q", "quit"):
            return "quit"
        print("  Unknown — use Enter, d, t, s, or q.")


# ---------------------------------------------------------------------------
# Commit logic — uses email["id"] directly (no search by from_field)
# ---------------------------------------------------------------------------

def commit_decisions(
    decisions: list[tuple[dict, EmailDecision]],
    service,
    label_map: dict[str, str],
) -> tuple[int, int, int]:
    """Apply confirmed decisions via Gmail API.

    Returns (tagged_count, deleted_count, error_count).
    """
    tagged = 0
    deleted = 0
    errors = 0

    for email, decision in decisions:
        msg_id = email.get("id", "")
        if not msg_id:
            print(f"  ⚠ No message id — skipping {email.get('from', '?')}")
            errors += 1
            continue

        try:
            if decision.is_delete:
                service.users().messages().trash(userId="me", id=msg_id).execute()
                deleted += 1
                print(f"  🗑  trashed: {email.get('from', '')[:50]}")

            elif isinstance(decision.action, list):
                label_ids: list[str] = []
                for a in decision.action:
                    label_name = a[4:] if a.startswith("tag:") else a
                    lid = label_map.get(label_name)
                    if lid:
                        label_ids.append(lid)
                    else:
                        print(f"  ⚠ label not found: {label_name}")

                if label_ids:
                    service.users().messages().modify(
                        userId="me",
                        id=msg_id,
                        body={"addLabelIds": label_ids},
                    ).execute()
                    tagged += 1
                    labels_str = ", ".join(
                        a[4:] if a.startswith("tag:") else a
                        for a in decision.action
                    )
                    print(f"  🏷  tagged: {email.get('from', '')[:50]} → {labels_str}")
                else:
                    print(f"  ⚠ no valid labels — skipping {email.get('from', '')[:50]}")
                    errors += 1
            else:
                errors += 1

        except Exception as exc:
            print(f"  ✗ API error on {email.get('from', '')[:50]}: {exc}")
            errors += 1

    return tagged, deleted, errors


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_cli() -> None:
    """Main interactive loop."""
    print("\n" + "=" * 64)
    print("  Gmail Agent — Interactive Tag & Commit")
    print("=" * 64)

    service = get_gmail_service()
    examples = load_examples("examples.json")
    label_map = load_labels(service)

    print(f"  {len(examples)} examples loaded | {len(label_map)} Gmail labels available")

    emails_to_fetch=50
    print(f"  Fetching {emails_to_fetch} unread emails from Google, please wait...")
    emails, unreadable, total = get_unread_emails(service, max_results=emails_to_fetch)
    print(f"  {len(emails)} unread emails fetched ({unreadable} unreadable)")

    if not emails:
        print("\n  No unread emails. Nothing to do.")
        return

    confirmed: list[tuple[dict, EmailDecision]] = []
    skipped = 0

    print("\n  Commands: Enter=accept  d=delete  t=tag  s=skip  q=quit\n")

    for i, email in enumerate(emails, start=1):
        # auto_tag_email expects key "snippet", emails from fetch_emails use "body_snippet"
        msg_for_tagging = {**email, "snippet": email.get("body_snippet", "")}
        decision = auto_tag_email(msg_for_tagging, examples, label_map)

        display_email(email, decision, i, len(emails))

        action = get_user_action()

        if action == "quit":
            print("\n  Quitting — processing confirmed decisions so far...")
            break

        elif action == "skip":
            skipped += 1
            print("  → skipped")
            continue

        elif action == "accept":
            if decision.action:
                confirmed.append((email, decision))
                print(f"  → accepted: {format_suggestion({'action': decision.action})}")
            else:
                skipped += 1
                print("  → no suggestion, skipping")

        elif action == "delete":
            override = EmailDecision(
                from_field=email.get("from", ""),
                subject=email.get("subject", ""),
                snippet=email.get("body_snippet", ""),
                action="delete",
                reasoning="User override",
                email_id=email.get("id", ""),
            )
            confirmed.append((email, override))
            print("  → delete (user override)")

        elif action == "tag":
            chosen = pick_labels(label_map, examples, [])
            if chosen:
                override = EmailDecision(
                    from_field=email.get("from", ""),
                    subject=email.get("subject", ""),
                    snippet=email.get("body_snippet", ""),
                    action=[f"tag:{l}" for l in chosen],
                    reasoning="User selected",
                    email_id=email.get("id", ""),
                )
                confirmed.append((email, override))
                print(f"  → {', '.join(override.action)}")
            else:
                skipped += 1
                print("  → cancelled, skipping")

    if confirmed:
        print(f"\n{'='*64}")
        print(f"  Committing {len(confirmed)} decisions to Gmail...")
        print("=" * 64)

        tagged, deleted, errors = commit_decisions(confirmed, service, label_map)

        # Build dedup sets from existing examples
        seen_ids: set[str] = set()
        seen_keys: set[tuple[str, str]] = set()
        for ex in examples:
            if ex.get("id"):
                seen_ids.add(ex["id"])
            else:
                seen_keys.add((ex.get("from", ""), ex.get("subject", "")))

        new_entries = []
        for _, d in confirmed:
            entry = d.as_json()
            eid = entry.get("id", "")
            fwd = entry.get("from", "")
            subj = entry.get("subject", "")
            if eid and eid in seen_ids:
                continue
            if (fwd, subj) in seen_keys:
                continue
            new_entries.append(entry)
            if eid:
                seen_ids.add(eid)
            seen_keys.add((fwd, subj))

        examples.extend(new_entries)
        save_examples(examples)

        print(f"\n{'='*64}")
        print(f"  ✓ Commit complete")
        print(f"    🏷  Tagged:   {tagged}")
        print(f"    🗑  Deleted:  {deleted}")
        print(f"    ✗  Errors:   {errors}")
        print(f"    →  Skipped:  {skipped}")
        print(f"    💾 Saved {len(new_entries)} decisions to examples.json")
        print("=" * 64)
    else:
        print(f"\n  No decisions committed. {skipped} emails skipped.")


def main() -> None:
    try:
        run_cli()
    except KeyboardInterrupt:
        print("\n\n  Interrupted — no changes committed.")
        sys.exit(130)


if __name__ == "__main__":
    main()
