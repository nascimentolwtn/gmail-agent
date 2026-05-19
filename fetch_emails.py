import json
import base64
from auth_test import get_gmail_service

def get_unread_emails(service, max_results=50, body_chars=300):
    results = service.users().messages().list(
        userId="me",
        q="is:unread",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        full = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"  # Get full payload, not just metadata
        ).execute()

        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}

        # Extract the first 'body_chars' characters of each email body
        def find_text_body(payload):
            """Walk MIME tree to find text/plain body."""
            # Leaf node with base64-encoded body data
            if "data" in payload and len(payload["data"]) >= 10:
                return payload["data"]

            # 'body' field can be a nested node for multipart/alternative messages
            if "body" in payload:
                body_val = payload["body"]
                if isinstance(body_val, dict) and "data" in body_val:
                    return find_text_body(body_val)

            if "parts" not in payload:
                return None

            # Recurse into parts - multipart/alternative has exactly 2 parts
            for part in payload.get("parts", []):
                result = find_text_body(part)
                if result is not None:
                    return result
            return None

        body_data = find_text_body(full["payload"])

        if not body_data:
            continue  # No text body found, skip this email

        # Decode base64 and get first 'body_chars' chars
        try:
            full_body = base64.b64decode(body_data).decode('utf-8', errors='ignore')
            body_snippet = full_body[:body_chars].strip()
        except (ValueError, UnicodeDecodeError):
            continue

        label_ids = full.get("labelIds", [])

        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body_snippet": body_snippet,  # First 150 chars of the email content
            "labels": label_ids
        })

    return emails

if __name__ == "__main__":
    service = get_gmail_service()
    emails = get_unread_emails(service, max_results=10)

    for i, email in enumerate(emails):
        print(f"\n[{i+1}] From:             {email['from']}")
        print(f"     Subject:       {email['subject']}")
        print(f"     Body snippet:  {repr(email['body_snippet'])}")
        print(f"     Date:          {email['date']}")
        print(f"     Labels:        {email['labels']}")

    # Debug dump the first email's full payload structure (first 50 levels)
    if emails:
        print("\n--- DEBUG: Full payload for first email ---")
        def dump_payload(payload, indent=0):
            prefix = "  " * indent
            item = payload or {}
            has_body = isinstance(item.get("data"), str)
            key = "body" if has_body else ("parts" if "parts" in item else None)

            print(f"{prefix}has_body={has_body}, has_parts={'yes' if 'parts' in item else 'no'}")
            print(f"{prefix}  mimeType={item.get('mimeType')!r}")
            if has_body:
                data = item["data"][:50]
                print(f"{prefix}  data (base64)={data}")

            # Walk all parts recursively, showing first few of each type
            for i, part in enumerate(item.get("parts", []), start=1):
                dump_payload(part, indent + 2)

        msg_data = emails[0]["id"]
        raw = service.users().messages().list(userId="me", maxResults=1).execute()["messages"]
        if not raw:
            print("[ERROR] No messages found!")
        else:
            payload = service.users().messages().get(
                userId="me", id=raw[0]["id"], format="full"
            ).execute()["payload"]

            dump_payload(payload, indent=0)