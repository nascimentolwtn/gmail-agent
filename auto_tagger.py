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
    email_id: str = ""                       # Gmail message id for deduplication

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
        if self.email_id:
            out["id"] = self.email_id
        if self.reasoning:
            # truncate to ~500 chars so it fits nicely in logs / audits
            out["reasoning"] = (self.reasoning + "...")[:500]
        return out


# ---------------------------------------------------------------------------
# Core reasoning engine
# ---------------------------------------------------------------------------

def load_examples(path: str) -> list[dict]:
    """Load the examples.json file. Returns [] if missing or invalid."""
    if not os.path.exists(path):
        return []
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


def _ascii_fold(text: str) -> str:
    """Strip diacritics so 'Família' matches 'familia'."""
    return text.translate(str.maketrans(
        "àáâãäåèéêëìíîïòóôõöùúûüýÿñç",
        "aaaaaaeeeeiiiiooooouuuuyync"))


def _example_similarity_score(msg: dict, ex: dict) -> float:
    """Score how similar an example is to the incoming email.

    Signals (weighted):
      +10  sender name match (exact or substring)
      +5   sender domain match
      +3   per shared subject keyword
      +1   per shared body/snippet keyword
    """
    score = 0.0
    msg_from = _ascii_fold((msg.get("from_field") or msg.get("from", "")).lower())
    msg_subj = _ascii_fold((msg.get("subject", "") or "").lower())
    msg_body = _ascii_fold((msg.get("snippet", "") or "").lower())

    ex_from = _ascii_fold((ex.get("from", "") or "").lower())
    ex_subj = _ascii_fold((ex.get("subject", "") or "").lower())
    ex_body = _ascii_fold((ex.get("snippet", "") or ex.get("body_snippet", "") or "").lower())

    # sender match
    if ex_from and (ex_from in msg_from or msg_from in ex_from):
        score += 10.0
    else:
        # domain match: extract @domain from sender
        msg_domain = msg_from.split("@")[-1] if "@" in msg_from else ""
        ex_domain = ex_from.split("@")[-1] if "@" in ex_from else ""
        if msg_domain and msg_domain == ex_domain:
            score += 5.0

    # subject keyword overlap
    if ex_subj and msg_subj:
        ex_words = set(re.findall(r"\w+", ex_subj))
        msg_words = set(re.findall(r"\w+", msg_subj))
        score += 3.0 * len(ex_words & msg_words)

    # body/snippet keyword overlap
    if ex_body and msg_body:
        ex_words = set(re.findall(r"\w+", ex_body))
        msg_words = set(re.findall(r"\w+", msg_body))
        score += 1.0 * len(ex_words & msg_words)

    return score


def _select_similar_examples(msg: dict, examples: list[dict], max_examples: int = 9) -> list[dict]:
    """Pick the most similar examples to the incoming email by content overlap.

    Scores every example on sender + subject + body similarity, then returns
    the top *max_examples* (preserving original order for stable few-shot context).
    """
    if len(examples) <= max_examples:
        return list(examples)

    scored = [(ex, _example_similarity_score(msg, ex)) for ex in examples]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    # take top-N, then re-sort by original position so the LLM sees chronological order
    top = scored[:max_examples]
    top_indices = {id(ex) for ex, _ in top}
    return [ex for ex in examples if id(ex) in top_indices]


def pick_labels_from_prompt(result: dict, examples: list[dict], label_map: dict, max_examples: int = 9) -> Optional[list[str]]:
    """Ask a small LLM to decide the best tag(s) given current email and similar past decisions.

    Few-shot examples are selected by content similarity (sender + subject + body overlap).
    The model sees what tags were applied to similar emails and *reasons* about whether
    the same tags, a subset, or none (delete) should apply to the current email.
    """

    if not LLAMA_URL or not re.match(r"^http://[\w.]+:\d+", LLAMA_URL):
        # no LLM available — just return empty, caller decides what to do with "auto" mode
        return []

    labels_list = ", ".join(label_map.keys())[:400] if label_map else ""  # keep prompt under model's context limit

    # select the most *similar* examples instead of just the last N
    similar_examples = _select_similar_examples(result, examples, max_examples=max_examples)

    # build few-shot context — include sender, subject, body snippet, AND the action taken
    # so the model can learn *why* certain tags were applied
    few_shot_lines = []
    for ex in similar_examples:
        ex_from = ex.get("from", "")
        ex_subj = ex.get("subject", "")
        ex_snip = (ex.get("snippet", "") or ex.get("body_snippet", ""))[:150]
        ex_action = ex.get("action", "")
        if isinstance(ex_action, list):
            ex_action = ", ".join(ex_action)
        few_shot_lines.append(
            f"  Email: From={ex_from!r}  Subject={ex_subj!r}\n"
            f"  Snippet: {ex_snip!r}\n"
            f"  → Action: {ex_action}"
        )
    examples_text = "\n\n".join(few_shot_lines) if few_shot_lines else ""

    # compose system prompt — explicitly tell the model to *reason*, not just copy
    system_prompt: str = (
        "/no_think\n"
        "You are an email tagger. You will see the current email and several past\n"
        "emails that are similar (same sender, similar subject/body). For each past\n"
        "email you see what action was taken (which tags were applied, or delete).\n\n"
        "Your job is to REASON about whether the same tags should apply to the\n"
        "current email:\n"
        "  - Apply ALL tags from a similar email if the content matches closely\n"
        "  - Apply ONLY SOME tags if only part of the pattern matches\n"
        "  - Return null (delete/skip) if the email is different enough\n\n"
        + (f"  Similar past emails and their actions:\n{examples_text}\n\n" if examples_text else "")
        + (f"  Available labels: {labels_list}\n\n" if labels_list else "")
        + "  RULES:\n"
        "  • Return ONLY valid JSON — no explanation, no markdown code fences\n"
        '  • Format: {"labels":[...], "reason":"..."} OR null\n'
        '  • The "reason" field should briefly explain WHY you chose these labels\n'
        '    based on which past decisions influenced your choice (1-2 sentences)\n'
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

    # if find_text_part didn't work, fall back to snippet
    if not user_body:
        snippet = (result.get("snippet", "") or "")[:900]
        if snippet:
            user_body = f"From / Subject:\n  {result.get('from_field', '')} | {result.get('subject', '').strip()}\n\nSnippet:\n{snippet}"

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
            return [], ""

        out = json.loads(raw_text)   # we expect {"labels": [...] } or null
    except Exception:  # noqa: PERF203, try/except on LLM call — caller handles "no model" gracefully
        return [], ""

    if isinstance(out, list):
        return [], ""
    if out is None:
        return [], ""   # signal to delete / skip instead of tag
    if isinstance(out, dict):
        labels = out.get("labels", [])
        reason = out.get("reason", "")
        return labels, reason
    return [], ""


def _rule_based_tag(msg: dict, examples: list[dict], max_examples: int = 9, label_threshold: float = 0.5) -> tuple[Optional[list[str]], str]:
    """Fallback: score each label individually by similarity, return all above threshold.

    Unlike the old atomic-action approach, this scores each *label* independently
    so the same sender can yield different tags depending on subject/body context.
    Labels whose aggregate similarity score ≥ `label_threshold` × top_label_score
    are returned, letting multi-label cases surface naturally.

    Delete is only returned when it is the single dominant action (no competing
    tags within the threshold), since tag-vs-delete ambiguity is better handled
    by the LLM path.
    """
    if not examples:
        return None, ""

    # get the top-N most similar examples (same selection as LLM path)
    top_examples = _select_similar_examples(msg, examples, max_examples=max_examples)

    # filter to examples with a positive similarity score
    scored = [(ex, _example_similarity_score(msg, ex)) for ex in top_examples]
    relevant = [(ex, s) for ex, s in scored if s > 0]

    if not relevant:
        return None, ""

    # score each individual label (not atomic action strings) by similarity
    label_scores: dict[str, float] = {}
    delete_score = 0.0
    for ex, score in relevant:
        action = ex.get("action", "")
        if isinstance(action, str):
            action = [action]
        if isinstance(action, list):
            for a in action:
                a_str = str(a).strip()
                if not a_str:
                    continue
                if a_str.lower() == "delete":
                    delete_score += score
                else:
                    m = re.match(r"^tag:(.+)$", a_str)
                    name = m.group(1) if m else a_str
                    label_scores[name] = label_scores.get(name, 0) + score

    if not label_scores and delete_score == 0:
        return None, ""

    # sort labels by descending score
    sorted_labels = sorted(label_scores, key=label_scores.get, reverse=True)  # type: ignore[arg-type]
    top_score = label_scores[sorted_labels[0]] if sorted_labels else 0.0

    # keep labels within threshold of the top score
    keep_threshold = top_score * label_threshold
    top_labels = [l for l in sorted_labels if label_scores[l] >= keep_threshold]

    # delete wins only if it outscores all tags combined (strong signal)
    if delete_score > 0 and delete_score > top_score:
        top_matches = sorted(relevant, key=lambda pair: pair[1], reverse=True)[:3]
        match_summaries = []
        for ex, score in top_matches:
            ex_from = ex.get("from", "")
            ex_action = ex.get("action", "")
            if isinstance(ex_action, list):
                ex_action = ", ".join(ex_action)
            match_summaries.append(f"  - From={ex_from!r} → {ex_action} (score={score:.1f})")
        reason = "Rule-based (delete dominates):\n" + "\n".join(match_summaries)
        return ["delete"], reason

    if not top_labels:
        return None, ""

    # build reason from the top matching examples + per-label scores
    top_matches = sorted(relevant, key=lambda pair: pair[1], reverse=True)[:3]
    match_summaries = []
    for ex, score in top_matches:
        ex_from = ex.get("from", "")
        ex_action = ex.get("action", "")
        if isinstance(ex_action, list):
            ex_action = ", ".join(ex_action)
        match_summaries.append(f"  - From={ex_from!r} → {ex_action} (score={score:.1f})")
    label_detail = ", ".join(f"{l}={label_scores[l]:.1f}" for l in top_labels)
    reason = f"Rule-based similarity scores: {label_detail}\n" + "\n".join(match_summaries)

    return top_labels, reason


def auto_tag_email(
    msg: dict[str, any],  # type: ignore[type-arg]
    examples: list[dict] = (),     # e.g. [ {"from": "...", "action":"tag:A"} ]
    label_map: Optional[dict[str, str]] = None,
    max_examples: int = 9,
) -> EmailDecision:
    """Predict and return the best tag(s) for a single email given prior decisions."""

    from_field = msg.get("from", "")[:200]
    subject = msg.get("subject", "")[:400].replace("\n", " ")
    snippet = msg.get("snippet", "")
    email_id = msg.get("id", "")

    if not examples:
        # no training data yet — ask model to inspect first few chars only
        labels, reason = pick_labels_from_prompt(
            {"from_field": "", "subject": f"{msg.get('subject','')[:300]}", "snippet": ""},
            examples, label_map, max_examples,
        )
    else:
        labels, reason = pick_labels_from_prompt(msg, examples, label_map, max_examples)

    # fall back to rule-based matching when LLM is unavailable
    if not labels:
        labels, reason = _rule_based_tag(msg, examples, max_examples)

    if not labels:
        return EmailDecision(
            from_field=from_field,
            subject=subject,
            snippet=snippet,
            action=None,
            reasoning="",
            email_id=email_id,
        )

    # handle delete
    if labels == ["delete"] or labels == "delete":
        return EmailDecision(
            from_field=from_field,
            subject=subject,
            snippet=snippet,
            action="delete",
            reasoning=reason,
            email_id=email_id,
        )

    return EmailDecision(
        from_field=from_field,
        subject=subject,
        snippet=snippet,
        action=[f"tag:{l}" for l in labels],
        reasoning=reason,
        email_id=email_id,
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
