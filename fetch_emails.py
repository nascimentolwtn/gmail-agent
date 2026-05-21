import re
import base64
import quopri
from auth_test import get_gmail_service

def _message_to_email(service, msg, body_chars):
    """Fetch one message by id and return an email dict, or None if unreadable."""
    full = service.users().messages().get(
        userId="me",
        id=msg["id"],
        format="full",
    ).execute()

    headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
    result = find_text_part(full["payload"])

    if not result:
        snippet = full.get("snippet", "").strip()
        if not snippet:
            return None
        body_snippet = snippet[:body_chars]
    else:
        data, transfer_enc, mime_type = result
        try:
            full_body = decode_part(data, transfer_enc)
            if mime_type == "text/html":
                full_body = strip_html(full_body)
            body_snippet = full_body[:body_chars].strip()
        except Exception as e:
            body_snippet = full.get("snippet", f"[Decode error: {e}]")[:body_chars]

    return {
        "id": msg["id"],
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "body_snippet": body_snippet,
        "labels": full.get("labelIds", []),
    }


def get_unread_emails(service, max_results=50, body_chars=300):
    results = service.users().messages().list(
        userId="me",
        q="is:unread",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []
    unreadable = 0

    for msg in messages:
        email = _message_to_email(service, msg, body_chars)
        if email is None:
            unreadable += 1
        else:
            emails.append(email)

    total = len(messages)
    return emails, unreadable, total


def find_text_part(payload, preferred="text/plain"):
    """Walk MIME tree. Returns (data, transfer_enc, mime_type) or None."""
    mime_type = payload.get("mimeType", "")

    if mime_type in ("text/plain", "text/html"):
        body = payload.get("body", {})
        data = body.get("data")
        if data:
            part_headers = {
                h["name"].lower(): h["value"]
                for h in payload.get("headers", [])
            }
            transfer_enc = part_headers.get("content-transfer-encoding", "base64").lower()
            return data, transfer_enc, mime_type

    for part in payload.get("parts", []):
        result = find_text_part(part, preferred)
        if result is not None:
            return result

    return None


def decode_part(data, transfer_enc):
    raw = base64.urlsafe_b64decode(data + "==")
    if transfer_enc == "quoted-printable":
        return quopri.decodestring(raw).decode("utf-8", errors="ignore")
    return raw.decode("utf-8", errors="ignore")


def strip_html(html):
    """Minimal HTML to plain text."""
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&zwnj;", "", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)  # other HTML entities
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_unread_emails_paginated(service, page_token=None, batch_size=20, body_chars=300):
    """Fetch one page of unread emails.

    Returns (emails, unreadable, total, next_page_token).
    When next_page_token is None there are no more pages.
    """
    kwargs = dict(userId="me", q="is:unread", maxResults=batch_size)
    if page_token:
        kwargs["pageToken"] = page_token

    results = service.users().messages().list(**kwargs).execute()
    messages = results.get("messages", [])
    next_page_token = results.get("nextPageToken")
    total = results.get("resultSizeEstimate", 0)

    emails = []
    unreadable = 0

    for msg in messages:
        email = _message_to_email(service, msg, body_chars)
        if email is None:
            unreadable += 1
        else:
            emails.append(email)

    return emails, unreadable, total, next_page_token


if __name__ == "__main__":
    service = get_gmail_service()
    emails, unreadable, total = get_unread_emails(service, max_results=100, body_chars=200)

    for i, email in enumerate(emails):
        print(f"\n[{i+1}] From:             {email['from']}")
        print(f"     Subject:       {email['subject']}")
        print(f"     Body snippet:  {repr(email['body_snippet'])}")
        print(f"     Date:          {email['date']}")
        print(f"     Labels:        {email['labels']}")

    print(f"Total unreadables = {unreadable}/{total} = {unreadable/total*100:.1f}%")
