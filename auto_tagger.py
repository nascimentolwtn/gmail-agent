# auto_tagger.py — Auto-Tagging Module using few-shot learning on user's tagged emails

"""
Auto-tagging module that bypasses interactive loop and predicts tags for emails,
then applies them via Gmail API. Uses top-N most-frequently-used labels from examples,
plus a small LLM call to match current email content against past decisions.
"""


from __future__ import annotations
import os
import json
import re
import string

from typing import Optional
from dataclasses import dataclass, field
from collections import Counter

from googleapiclient.errors import HttpError
from fetch_emails import get_unread_emails, find_text_part  # reuse Gmail parser


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
EXAMPLES_FILE = os.getenv("AUTO_TAGGER_EXAMPLES", "examples.json")
LLAMA_URL = os.getenv(
    "AUTO_TAGGER_LLM_URL", "http://localhost:11434/v1/messages"
)  # llama.cpp default


@dataclass
class EmailDecision:
    """Result of auto-tagging a single email."""

    from_field: str
    subject: str
    snippet: str
    action: Optional[str] = None              # "delete" or list of labels like "tag:LABEL1, tag:LABEL2"
    reasoning: str = ""                      # what the model thought before deciding

    @property
    def is_delete(self) -> bool:
        return self.action == "delete"

    def as_json(self) -> dict:
        out: dict[str, any] = {
            "from": self.from_field,
            "subject": self.subject,
            "snippet": self.snippet[:200],
            "action": self.action or "",
        }
        if self.reasoning:
            # truncate to ~500 chars so it fits nicely in logs / audits
            out["reasoning"] = (self.reasoning + "...")[:500]
        return out


# ---------------------------------------------------------------------------
# Core reasoning engine
# ---------------------------------------------------------------------------

def load_examples(path: str) -> list[dict]:
    """Load the examples.json file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # normalize so each example is a single-item dict (original format allows lists)
    if isinstance(data, list):
        return [{"action": a} if not isinstance(a, dict) else a for a in data]
    return []


def extract_user_labels(examples: list[dict]) -> Counter[str]:
    """Count how often each label appears across examples."""

    counter = Counter()
    for ex in examples:
        actions = (ex["action"] if isinstance(ex["action"], list) else [ex["action"]])
        for a in actions:
            m = re.match(r"^tag:(.+)$", str(a))
            if m:
                counter[m.group(1).lower()] += 1

    return counter


def pick_labels_from_prompt(result: dict, examples: list[dict], label_map: dict) -> Optional[list[str]]:
    """Ask a small LLM to decide the best tag(s) given current email and top-k past decisions."""

    if not LLAMA_URL or not re.match(r"^http://\d+:\d+", LLAMA_URL):
        # no LLM available — just return empty, caller decides what to do with "auto" mode
        return []

    labels_list = ", ".join(label_map.keys())[:400]  # keep prompt under model's context limit

    # pick up to ~25 most-recent decisions that were *tagged* (not deleted) — they are the strongest signal
    tagged: list[dict] = [
        {k: v for k, v in ex.items() if k != "action"}
        for ex in examples[-100:]
    ][:25]

    # compute a few features to feed into the LLM system prompt so it can be more consistent:
    freq_labels = extract_user_labels(examples)
    recent = [label_map.get(l, l) for l in list(freq_labels.most_common(8)) if l.lower() in label_map]

    # build a short "style" string the model uses as a few-shot reference (top 4 labels by frequency)
    style_ref: str = ""
    if freq_labels and recent:
        top_n = min(len(recent), 4)
        style_ref = f"  Recent user interest in:\n    • {', '.join(recent[:top_n])}\n\n"

    # compose system prompt — teaches model what output format to emit, e.g. {"labels":[...]}" or null
    system_prompt: str = (
        "/no_think\n"
        f"You are an email tagger that uses few-shot reasoning based on the user's labeled examples.\n"
        f"  Available labels:\n{labels_list}\n\n" + style_ref +
        "  RULES:\n"
        "  • Return ONLY valid JSON — no explanation, no markdown code fences\n"
        '  • Format: {"labels":[...]} OR null (use null if delete or uncertain)\n'
    )

    user_body: str = ""
    try:
        # use snippet + subject; strip any HTML to keep the prompt clean for a text-based model
        u = find_text_part(result)  # type: ignore[call-overload]
        if u is not None and len(u) >= 3:
            data, enc, _ = u
            raw = (data + "==" * (len(data) % 4)).decode("utf-8", errors="ignore")[:900].strip()
            user_body = f"From / Subject:\n  {result.get('from_field', '')} | {result.get('subject', '').strip()}\n\nContent (plain):\n{raw}"
    except Exception:
        pass

    payload: dict[str, any] = {
        "model": "local",
        "max_tokens": 512,       # we only need a JSON block, not long reasoning
        "thinking": {"type": "disabled"},   # llama.cpp flag — ignored if unsupported
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_body}],
    }

    try:
        import requests; r = requests.post(LLAMA_URL, json=payload, headers={"x-api-key": "local"})
        data = r.json()  # type: ignore[union-attr]
        raw_text = None
        if isinstance(data.get("content"), list):
            for block in data["content"]:  # type: ignore[attr-defined]
                if isinstance(block, dict) and (block.get("type") == "text" or not block.get("type")):
                    if isinstance(block.get("text"), str):
                        raw_text = block["text"].strip()
                        break
        elif isinstance(data.get("choices", [{}])[0].get("message", {}).get("content"), str):  # type: ignore[attr-defined]
            raw_text = data["choices"][0]["message"]["content"]
        if not raw_text or "{" not in raw_text:
            return []

        out = json.loads(raw_text)   # we expect {"labels": [...] } or null
    except Exception as e:  # noqa: PERF203, try/except on LLM call — caller handles "no model" gracefully
        pass

    if isinstance(out, list):
        return []
    if out is None:
        return []   # signal to delete / skip instead of tag


def auto_tag_email(
    msg: dict[str, any],  # type: ignore[type-arg]
    examples: list[dict] = (),     # e.g. [ {"from": "...", "action":"tag:A"} ]
    label_map: Optional[dict[str, str]] = None,
) -> EmailDecision:
    """Predict and return the best tag(s) for a single email given prior decisions."""

    if not examples:
        # no training data yet — ask model to inspect first few chars only so it can say "delete" or "tag common patterns"
        labels = pick_labels_from_prompt({"from_field": "", "subject": f"{msg.get('subject','')[:100]}", "snippet":""}, examples, label_map)  # type: ignore[union-attr]
    else:
        labels = pick_labels_from_prompt(msg, examples, label_map)

    if not labels:
        return EmailDecision(
            from_field=msg.get("from", "")[:200],
            subject=msg.get("subject", "")[:400].replace("\n", " "),
            snippet=msg.get("snippet", ""),
            action=None,
        )

    # strip "tag:" prefix if caller prefers raw names — callers of apply_decision() handle this
    return EmailDecision(
        from_field=msg.get("from", "")[:200],
        subject=msg.get("subject", "")[:400].replace("\n", " "),
        snippet=msg.get("snippet", ""),
        action=[f"tag:{l}" for l in labels],
    )


# ---------------------------------------------------------------------------
# Gmail API integration — apply or undo a decision (requires gmail.modify scope)
# ---------------------------------------------------------------------------

def get_gmail_service() -> any:  # type: ignore[return-type]
    from google_auth_oauthlib.flow import InstalledAppFlow     # noqa: F401
    from googleapiclient.discovery import build                   # noqa: F401
    from google.auth.transport.requests import Request            # noqa: F401
    from google.oauth2.credentials import Credentials             # noqa: F401

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify"   # needed to apply labels / delete
    ]

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0, title="Auto-Tagger")

        with open("token.json", "w") as f:
            f.write(creds.to_json())  # noqa: S105 — user-authorized token; not shared / pushed
    return build("gmail", "v1", credentials=creds)


def apply_decision(decision: EmailDecision, service: any = None) -> bool:  # type: ignore[type-arg]
    """Apply the tagged labels (or delete) via Gmail API — returns True on success."""

    if not decision.action or decision.is_delete == False:   # "delete" is a string; also guard against empty list
        return True

    service = get_gmail_service() if not service else service  # noqa: F841
    try:
        messages_query: str = (" from:\"*" + decision.from_field.replace("@", "") + "\"")[:200]
        for msg in service.users().messages().list(userId="me", q=messages_query).execute().get("messages", [])[:5]:
            res = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            if decision.action == "delete":
                service.users().messages().delete(userId="me", id=msg["id"]).execute()
                return True

            labels_to_add: list[str] = []
            for a in (decision.action if isinstance(decision.action, list) else [decision.action]):
                if re.match(r"^tag:[A-Za-z][^:\n]*$", str(a)):  # e.g. "tag:LABEL"
                    m = re.match(r"^tag:(.+)$", str(a)); lab_id: Optional[str] = (m.group(1) if m else None)   # type: ignore[assignment]
                    if lab_id and res.get("labelIds"):
                        labels_to_add.append(f"labelIds:{lab_id}")

            if not labels_to_add:
                return True

            service.users().messages().patch(userId="me", id=msg["id"], body={"addLabels": list(labels_to_add)}).execute()
            return True

        # exact match failed — fall back to scanning all messages (slow, last resort)
        for msg in service.users().messages().list(userId="me").execute().get("messages", [])[:50]:  # noqa: PERF203
            res = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            if decision.action == "delete":
                service.users().messages().delete(userId="me", id=msg["id"]).execute(); return True

            labels_to_add: list[str] = []
            for a in (decision.action if isinstance(decision.action, list) else [decision.action]):
                m = re.match(r"^tag:[A-Za-z][^:\n]*$", str(a)); lab_id: Optional[str] = (m.group(1) if m else None)   # type: ignore[assignment]
                if lab_id and res.get("labelIds"):
                    labels_to_add.append(f"labelIds:{lab_id}")

            if not labels_to_add: return True

            service.users().messages().patch(userId="me", id=msg["id"], body={"addLabels": list(labels_to_add)}).execute()
        return False

    except HttpError as e:  # noqa: PERF203, try/except — Gmail API errors are not always fatal
        print(f" [API] apply failed on {decision.from_field}: {e.reason}")
        return False


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main():
    """Command-line interface: auto-tag unread emails and save results to examples.json."""
    import sys; sys.path.insert(0, ".")   # so imports like fetch_emails work in a fresh shell

    from fetch_emails import get_unread_emails     # noqa: F401, F821
    if not os.getenv("AUTO_TAGGER_SKIP_AUTH"):
        try:
            _ = get_gmail_service()
        except OSError as e:  # no credentials / auth error — user must authenticate first; we do NOT crash the tool
            print(f"\n⚠ Not authenticated yet. Run 'python auth_test.py' once, then retry.\n{e}", file=sys.stderr)

    examples = load_examples(EXAMPLES_FILE); label_map: dict[str, str] = {}  # noqa: F811,F405
    if not os.getenv("AUTO_TAGGER_SKIP_LABELS") and get_gmail_service() is not None:
        try:
            res = get_gmail_service().users().labels().list(userId="me").execute()
            label_map.update(
                {l["name"]: l["id"] for l in (res.get("labels", []) or [])} if isinstance(res, dict) else {}
            )
        except Exception:  pass

    print(f"\n{'='*60}")
    print(f"Auto-Tagger — processing unread emails")
    print(f"{len(examples)} examples loaded | {label_map} user labels available" if label_map else f"{len(examples)} examples loaded")
    print('='*60)

    decisions: list[EmailDecision] = []  # noqa: F811,F405

    emails, unreadable, total = get_unread_emails(get_gmail_service())
    for i, email in enumerate(emails):
        try:
            decision = auto_tag_email({**email, "snippet": email.get("body_snippet", "")}, examples, label_map)   # noqa: F811,F405
            if not decision.action and decision.from_field.lower() not in ("from:", "from field:"):  # skip empty decisions
                decisions.append(decision); print(f"\n[{i+1}/{total}] From: {email['from']}")   # noqa: F811,F405

            snippet = (decision.snippet + "").strip()[:72] if decision.snippet else ""  # noqa: F811
            action_str: str = repr(decision.action) or "(none)"   # noqa: F811,F405
            reason_preview = (decision.reasoning.strip() + "")[:60].replace("\n", " ") if decision.reasoning else ""  # noqa: F811

        except Exception as e:
            pass; print(f" [ERROR] email {i}: {e}", file=sys.stderr)   # noqa: F811,F405
            continue

        from_snip = (decision.from_field or "")[:72].replace("\n", " ").strip()  # noqa: F811
        print(f"    [{len(decisions)+1}/{max(1,total)}] From   {from_snip}")
        print(f"                Subject              Action")
        print(f"                      │{snippet!r:<65}│ {action_str}")
        if reason_preview:  # noqa: PERF203, try/except — show a short reasoning preview for the user to validate
            print(f"                     {'─' * (71 - len(reason_preview))}    │  • {reason_preview!r:<65}")

    n = len(decisions)   # noqa: F811,F405
    if not decisions and total > 0:
        print(f"\n✗ No decisions to make (no tags or delete actions found)."); return   # noqa: PERF203, try/except — "no decisions" is a success path

    examples.extend(decisions); save_examples(examples)
    print(f"\n{'='*60}")
    print(f"✓ Saved {len(decisions)} decisions to {EXAMPLES_FILE}");   # noqa: F811,F405,F821
    print(f"{total - len(emails):>3} unreadables = {(total-len(emails))/max(1,total)*100:.1f}%")
    print('='*60)
