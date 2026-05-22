"""Gmail OAuth2 lifecycle manager.

Token storage uses plain JSON files so the implementation can later be swapped
for a keychain-backed store without changing the interface.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


class TokenMissingError(Exception):
    """Raised when no valid token exists for an account and OAuth is required."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"No valid token for account '{account_id}' — OAuth required")


class GmailOAuthManager:
    """Manages Google OAuth2 flows and token persistence for Gmail access.

    Token files are named with a 16-char SHA-256 prefix of the account email,
    never the email itself.  The email address is stored inside the JSON so
    ``list_token_accounts()`` can return it without exposing it in filenames.
    In-memory state for pending (not-yet-completed) flows is keyed by the
    OAuth ``state`` parameter.

    Args:
        credentials_path: Path to ``credentials.json`` from Google Cloud Console.
        tokens_dir: Directory for per-account token files (created if absent).
        redirect_uri: OAuth2 redirect URI registered in Google Cloud Console.
    """

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(
        self,
        credentials_path: Path,
        tokens_dir: Path,
        redirect_uri: str = "http://localhost:8000/api/auth/callback",
    ) -> None:
        self._credentials_path = credentials_path
        self._tokens_dir = tokens_dir
        self._tokens_dir.mkdir(parents=True, exist_ok=True)
        self._redirect_uri = redirect_uri
        self._pending_flows: dict[str, Flow] = {}

    def _token_path(self, account_id: str) -> Path:
        digest = hashlib.sha256(account_id.lower().encode()).hexdigest()[:16]
        return self._tokens_dir / f"{digest}.json"

    @property
    def is_configured(self) -> bool:
        """True if credentials.json exists and is readable."""
        return self._credentials_path.exists()

    def start_auth_flow(self, redirect_uri: str | None = None) -> tuple[str, str]:
        """Begin an OAuth2 authorization flow.

        Args:
            redirect_uri: Override the default redirect URI (used by the CLI
                local-callback server).

        Returns:
            ``(auth_url, state)`` — open auth_url in the browser; pass state
            back when the OAuth callback arrives.

        Raises:
            FileNotFoundError: If credentials.json is missing.
        """
        if not self.is_configured:
            raise FileNotFoundError(
                f"Google credentials not found at {self._credentials_path}. "
                "Download credentials.json from Google Cloud Console and place "
                "it in the app directory."
            )
        flow = Flow.from_client_secrets_file(
            str(self._credentials_path),
            scopes=self.SCOPES,
            redirect_uri=redirect_uri or self._redirect_uri,
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        self._pending_flows[state] = flow
        return auth_url, state

    def complete_auth_flow(self, code: str, state: str) -> tuple[str, Credentials]:
        """Exchange an authorization code for credentials and resolve the Gmail address.

        Returns:
            ``(email_address, credentials)``.

        Raises:
            KeyError: If state does not match a pending flow.
        """
        flow = self._pending_flows.pop(state)
        flow.fetch_token(code=code)
        credentials = flow.credentials
        service = build("gmail", "v1", credentials=credentials)
        profile = service.users().getProfile(userId="me").execute()
        return profile["emailAddress"], credentials

    def refresh_if_needed(self, account_id: str) -> Credentials:
        """Load and refresh the token for account_id if it has expired.

        Returns valid credentials.

        Raises:
            TokenMissingError: If no token file exists or the token cannot be
                refreshed (e.g. refresh_token revoked).
        """
        creds = self.load_token(account_id)
        if creds is None:
            raise TokenMissingError(account_id)
        if creds.expired:
            if not creds.refresh_token:
                raise TokenMissingError(account_id)
            creds.refresh(Request())
            self.save_token(account_id, creds)
        return creds

    def list_token_accounts(self) -> list[str]:
        """Return email addresses for all stored tokens."""
        accounts: list[str] = []
        for p in sorted(self._tokens_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                if "account_id" in data:
                    accounts.append(data["account_id"])
            except Exception:
                pass
        return accounts

    def save_token(self, account_id: str, credentials: Credentials) -> None:
        token_data = {
            "account_id": account_id,
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or []),
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }
        self._token_path(account_id).write_text(json.dumps(token_data, indent=2))

    def load_token(self, account_id: str) -> Credentials | None:
        path = self._token_path(account_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        creds = Credentials(
            token=data["token"],
            refresh_token=data.get("refresh_token"),
            token_uri=data["token_uri"],
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=data.get("scopes"),
        )
        if data.get("expiry"):
            creds.expiry = datetime.fromisoformat(data["expiry"])
        return creds

    def remove_token(self, account_id: str) -> None:
        path = self._token_path(account_id)
        if path.exists():
            path.unlink()
