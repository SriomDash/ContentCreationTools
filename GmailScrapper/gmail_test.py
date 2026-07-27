"""
Minimal Gmail read-only connection test.

Setup:
  pip install google-auth-oauthlib google-api-python-client
  Put your downloaded client_secret_*.json in the same folder, renamed to
  credentials.json (or edit CRED_FILE below).

Run:
  python gmail_test.py
A browser opens -> pick your Google account -> you'll see the "unverified app"
screen -> Advanced -> "go to (unsafe)" -> Allow. That's you authorizing your
own app. A token.json is saved so you won't re-auth every run (until it expires
~7 days in testing mode).

What it does: counts unread messages under a label and prints the latest few
subjects. Read-only. It cannot delete, archive, or send anything.
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CRED_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Change this to the Gmail label you put your newsletters under.
# Use "INBOX" first just to confirm the connection, then switch to your label.
LABEL = "INBOX"


def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CRED_FILE, SCOPES)
            PORT = 9090
            print("=" * 60)
            print("In Google Cloud console, open your Web OAuth client and make")
            print("sure this EXACT string is under Authorized redirect URIs:")
            print(f"    http://localhost:{PORT}/")
            print("(include the trailing slash). Save, then continue here.")
            print("=" * 60)
            creds = flow.run_local_server(port=PORT)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def main():
    service = get_service()

    # Resolve the label name to its ID.
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    label_id = next((l["id"] for l in labels if l["name"] == LABEL), None)
    if not label_id:
        print(f'Label "{LABEL}" not found. Available labels:')
        for l in labels:
            print("  -", l["name"])
        return

    # List a few recent messages under that label.
    resp = service.users().messages().list(
        userId="me", labelIds=[label_id], maxResults=5
    ).execute()
    msgs = resp.get("messages", [])
    print(f'Connected. Found {resp.get("resultSizeEstimate", 0)} messages under "{LABEL}".')
    print("Latest few subjects:")
    for m in msgs:
        full = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        print(f'  - {headers.get("Subject", "(no subject)")}  |  {headers.get("From", "")}')


if __name__ == "__main__":
    main()