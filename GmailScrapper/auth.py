"""
auth.py — reuse the EXISTING read-only Gmail auth.

Builds a Gmail API service from the token.json / credentials.json already in
this folder (google-auth-oauthlib flow, run_local_server on port 9090, as set up
in gmail_test.py). Refreshes the token if expired.

SAFETY: The scope is hardcoded to gmail.readonly and asserted at runtime. If the
existing token was ever minted with a broader scope, this raises instead of
silently using write access. This app has no code path that needs anything more
than read.
"""

import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CRED_FILE = "credentials.json"
TOKEN_FILE = "token.json"

# READ-ONLY. Do not add write/modify/delete/send scopes here. Ever.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_OAUTH_PORT = 9090


def _assert_readonly(creds):
    """Refuse to run with anything beyond gmail.readonly."""
    scopes = set(getattr(creds, "scopes", None) or [])
    if scopes and scopes != set(SCOPES):
        raise RuntimeError(
            "Refusing to run: token scopes are not read-only.\n"
            f"  expected: {SCOPES}\n  got:      {sorted(scopes)}\n"
            "This tool is strictly gmail.readonly. Delete token.json and "
            "re-auth with the read-only scope, or check credentials.json."
        )


def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Falls back to the same local-server flow used in gmail_test.py.
            # In normal use the existing token.json is reused and this never runs.
            flow = InstalledAppFlow.from_client_secrets_file(CRED_FILE, SCOPES)
            creds = flow.run_local_server(port=_OAUTH_PORT)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    _assert_readonly(creds)
    return build("gmail", "v1", credentials=creds)
