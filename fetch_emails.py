import json
import base64
from auth_test import get_gmail_service

def get_unread_emails(service, max_results=50):
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
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}

        # Extract the first 150 characters of each email body
        try:
            part = full["payload"].get("parts", [full.get("payload", {})])
            if isinstance(part, list):
                part = part[0]

            body_snippet = ""
            for i in range(3):  # Navigate through MIME tree up to 3 levels deep (text/plain)
                mime_part = part.get("body") or part.get("parts", [{}])[0].get("body", {})

                if "data" in mime_part:
                    body_snippet = mime_part["data"]
                    break
                elif isinstance(mime_part, dict):
                    part = mime_part.get("parts", [{}])[0]

            # Decode base64 and get first 150 chars
            try:
                full_body = base64.b64decode(body_snippet).decode('utf-8', errors='ignore')
                body_snippet = full_body[:150].strip()
            except (ValueError, UnicodeDecodeError):
                pass

        except Exception as e:
            body_snippet = f"[error extracting body]"

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
    emails = get_unread_emails(service, max_results=50)

    for i, email in enumerate(emails):
        print(f"\n[{i+1}] From:             {email['from']}")
        print(f"     Subject:       {email['subject']}")
        print(f"     Body snippet:  {repr(email['body_snippet'])}")
        print(f"     Date:          {email['date']}")
        print(f"     Labels:        {email['labels']}")