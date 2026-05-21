# review_emails.py
import json
import os
from collections import Counter
from auth_test import get_gmail_service
from fetch_emails import get_unread_emails
from suggest import suggest_action, format_suggestion

EXAMPLES_FILE = "examples.json"

def load_examples():
    if os.path.exists(EXAMPLES_FILE):
        with open(EXAMPLES_FILE, "r") as f:
            return json.load(f)
    return []

def save_examples(examples):
    with open(EXAMPLES_FILE, "w") as f:
        json.dump(examples, f, indent=2, ensure_ascii=False)

def load_labels(service):
    result = service.users().labels().list(userId="me").execute()
    labels = result.get("labels", [])
    user_labels = [l for l in labels if l["type"] == "user"]
    return {l["name"]: l["id"] for l in user_labels}

def get_recent_labels(examples, session_decisions=None, top_n=9):
    """Return most frequently used labels from saved + current session."""
    counter = Counter()
    all_decisions = examples + (session_decisions or [])
    for ex in all_decisions:
        actions = ex["action"] if isinstance(ex["action"], list) else [ex["action"]]
        for a in actions:
            if a.startswith("tag:"):
                counter[a[4:]] += 1
    return [label for label, _ in counter.most_common(top_n)]


def ordered_labels_for_picker(label_map, examples, session_decisions=None, top_n=9):
    """Return label names ordered: top-N frequent first, then remaining A–Z."""
    recent = get_recent_labels(examples, session_decisions, top_n)
    recent_valid = [n for n in recent if n in label_map]
    others = sorted([n for n in label_map if n not in recent_valid])
    return recent_valid + others

def pick_labels(label_map, examples, session_decisions=None):
    all_names = list(label_map.keys())
    ordered = ordered_labels_for_picker(label_map, examples, session_decisions)
    # section_break = how many of the ordered list are "recent" (top-N)
    recent_labels = set(get_recent_labels(examples, session_decisions))
    section_break_count = len([n for n in ordered if n in recent_labels])
    selected = []

    while True:
        # filter step
        filter_term = input("\n  Filter labels (ENTER to show recent): ").strip().lower()

        if filter_term == "c":
            return None

        if filter_term == "":
            display = ordered
            section_break = section_break_count
        else:
            display = [n for n in all_names if filter_term in n.lower()]
            section_break = None

        if not display:
            print("  No labels match — try again.")
            continue

        # print filtered/sorted list
        print()
        for i, name in enumerate(display):
            if section_break is not None and i == section_break and section_break > 0:
                print("  " + "─" * 30)
            check = "✓" if name in selected else " "
            star  = "★" if section_break is not None and i < (section_break or 0) else " "
            print(f"    {i+1:2}) [{check}]{star} {name}")

        if selected:
            print(f"\n  Selected: {', '.join(selected)}")

        print("\n  Enter number to toggle, ENTER to confirm, f to filter again, c to cancel.")

        while True:
            choice = input("  > ").strip().lower()

            if choice == "":
                if selected:
                    return selected
                else:
                    print("  No labels selected — pick at least one.")

            elif choice == "c":
                return None

            elif choice == "f":
                break  # go back to filter prompt

            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(display):
                    name = display[idx]
                    if name in selected:
                        selected.remove(name)
                        print(f"  − removed: {name}")
                    else:
                        selected.append(name)
                        print(f"  + added: {name}")
                    if selected:
                        print(f"  Selected: {', '.join(selected)}")
                else:
                    print("  Number out of range.")

            else:
                print("  Invalid — number, ENTER, f, or c.")

def review_emails(service):
    emails, unreadable, total = get_unread_emails(service, max_results=50)
    label_map = load_labels(service)
    examples = load_examples()

    print(f"\n{'='*60}")
    print(f"  Gmail Agent — Review Session")
    print(f"  {len(emails)} unread emails | {len(examples)} examples so far")
    print(f"{'='*60}")
    print("  Commands: d=delete  t=tag  s=skip  q=quit\n")

    session_decisions = []

    for i, email in enumerate(emails):
        print(f"\n[{i+1}/{len(emails)}]")
        print(f"  From:         {email['from']}")
        print(f"  Subject:      {email['subject']}")
        body_snippet = email.get('body_snippet', '')[:60].replace('\n', ' ')
        if len(body_snippet) > 60:
            body_snippet += "..."
        print(f"  Body snippet: {repr(body_snippet)}")
        print(f"  Date:         {email['date']}")

        # --- NEW: show LLM suggestion ---
        if len(examples) + len(session_decisions) >= 10:
            suggestion = suggest_action(email, examples + session_decisions, label_map)
            print(f"\n  💡 Suggestion: {format_suggestion(suggestion)}")
        else:
            print(f"\n  💡 Suggestion: (needs 10+ examples first)")
        # --------------------------------

        while True:
            cmd = input("\n  Action [d/t/s/q]: ").strip().lower()

            if cmd == "q":
                print("\n  Quitting — saving decisions so far...")
                _save_session(examples, session_decisions)
                return

            elif cmd == "s":
                print("  Skipped.")
                break

            elif cmd == "d":
                decision = {
                    "from": email["from"],
                    "subject": email["subject"],
                    "body_snippet": body_snippet,
                    "action": "delete"
                }
                session_decisions.append(decision)
                print("  → delete")
                break

            elif cmd == "t":
                chosen = pick_labels(label_map, examples, session_decisions)
                if chosen:
                    decision = {
                        "from": email["from"],
                        "subject": email["subject"],
                        "body_snippet": body_snippet,
                        "action": [f"tag:{l}" for l in chosen]
                    }
                    session_decisions.append(decision)
                    print(f"  → {', '.join(decision['action'])}")
                    break
                else:
                    print("  Cancelled — pick another action.")

            else:
                print("  Unknown command. Use d/t/s/q.")

    _save_session(examples, session_decisions)
    print(f"Total unreadables = {unreadable}/{total} = {unreadable/total*100:.1f}%")

def _save_session(examples, session_decisions):
    if session_decisions:
        examples.extend(session_decisions)
        save_examples(examples)
        print(f"\n  ✓ Saved {len(session_decisions)} decisions to {EXAMPLES_FILE}")
        print(f"  Total examples now: {len(examples)}")
    else:
        print("\n  No decisions to save.")

if __name__ == "__main__":
    service = get_gmail_service()
    review_emails(service)