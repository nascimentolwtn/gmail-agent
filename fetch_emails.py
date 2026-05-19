import json
import base64
import quopri
from auth_test import get_gmail_service

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
        full = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}

        def find_text_part(payload):
            """Walk MIME tree, return (data, encoding) for text/plain part."""
            mime_type = payload.get("mimeType", "")
            
            # Leaf text/plain node
            if mime_type == "text/plain":
                body = payload.get("body", {})
                data = body.get("data")
                if data:
                    # Read transfer encoding from part headers
                    part_headers = {
                        h["name"].lower(): h["value"]
                        for h in payload.get("headers", [])
                    }
                    transfer_enc = part_headers.get("content-transfer-encoding", "base64").lower()
                    return data, transfer_enc

            # Recurse into multipart/* parts
            for part in payload.get("parts", []):
                result = find_text_part(part)
                if result is not None:
                    return result

            return None

        result = find_text_part(full["payload"])

        if not result:
            unreadable += 1
            continue

        data, transfer_enc = result

        try:
            if transfer_enc in ("base64", ""):
                # Gmail always delivers base64 with URL-safe alphabet
                full_body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
            elif transfer_enc == "quoted-printable":
                # data is still base64-wrapped by Gmail; decode that first
                raw = base64.urlsafe_b64decode(data + "==")
                full_body = quopri.decodestring(raw).decode("utf-8", errors="ignore")
            elif transfer_enc == "8bit" or transfer_enc == "7bit":
                raw = base64.urlsafe_b64decode(data + "==")
                full_body = raw.decode("utf-8", errors="ignore")
            else:
                full_body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")

            body_snippet = full_body[:body_chars].strip()

        except Exception as e:
            body_snippet = f"[Decode error: {e}]"
            unreadable += 1

        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body_snippet": body_snippet,
            "labels": full.get("labelIds", [])
        })

    total = len(messages)
    print(f"Total unreadables = {unreadable} / {total} = {unreadable/total*100:.1f}%")
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
