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
        label_ids = full.get("labelIds", [])

        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "labels": label_ids
        })

    return emails

if __name__ == "__main__":
    service = get_gmail_service()
    emails = get_unread_emails(service, max_results=50)

    for i, email in enumerate(emails):
        print(f"\n[{i+1}] From:    {email['from']}")
        print(f"     Subject: {email['subject']}")
        print(f"     Date:    {email['date']}")
        print(f"     Labels:  {email['labels']}")