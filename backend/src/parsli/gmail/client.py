"""Gmail API client — fetches raw message data from the Gmail API."""

import base64
import re
from html.parser import HTMLParser

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-plain-text converter using stdlib only."""

    _SKIP_TAGS = frozenset({"style", "script", "head"})
    _BLOCK_TAGS = frozenset({"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", raw)).strip()


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
    except Exception:
        pass
    return stripper.get_text()


def _decode_b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


class GmailClient:
    """Thin wrapper around the Gmail API for message retrieval.

    Args:
        credentials: Valid, non-expired OAuth2 credentials.
    """

    def __init__(self, credentials: Credentials) -> None:
        self._service = build("gmail", "v1", credentials=credentials)

    def list_message_ids(self, query: str) -> list[str]:
        """Return all message IDs matching *query*, paginating automatically."""
        ids: list[str] = []
        page_token: str | None = None
        while True:
            params: dict = {"userId": "me", "q": query, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            resp = self._service.users().messages().list(**params).execute()
            ids.extend(msg["id"] for msg in resp.get("messages", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return ids

    def get_history(self, start_history_id: str) -> tuple[list[str], str | None]:
        """Return (new_message_ids, latest_history_id) since start_history_id."""
        new_ids: list[str] = []
        latest: str | None = None
        try:
            resp = self._service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
            ).execute()
            latest = resp.get("historyId")
            for record in resp.get("history", []):
                for added in record.get("messagesAdded", []):
                    new_ids.append(added["message"]["id"])
        except Exception:
            pass
        return new_ids, latest

    def fetch_raw(self, message_id: str) -> dict:
        """Fetch the full raw message payload from Gmail."""
        return self._service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

    def get_history_id(self) -> str | None:
        """Return the current mailbox historyId."""
        try:
            profile = self._service.users().getProfile(userId="me").execute()
            return profile.get("historyId")
        except Exception:
            return None

    def get_account_email(self) -> str | None:
        """Return the authenticated account's email address."""
        try:
            profile = self._service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress")
        except Exception:
            return None

    @staticmethod
    def extract_headers(raw: dict) -> dict[str, str]:
        return {
            h["name"]: h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }

    @staticmethod
    def extract_body(payload: dict) -> str:
        """Recursively extract plain text from a Gmail message payload.

        Prefers text/plain; falls back to HTML-stripped text/html.
        """
        mime = payload.get("mimeType", "")

        if mime == "text/plain":
            data = payload.get("body", {}).get("data", "")
            return _decode_b64(data) if data else ""

        if mime == "text/html":
            data = payload.get("body", {}).get("data", "")
            return _strip_html(_decode_b64(data)) if data else ""

        parts = payload.get("parts", [])
        plain = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
        if plain:
            return GmailClient.extract_body(plain)
        html = next((p for p in parts if p.get("mimeType") == "text/html"), None)
        if html:
            return GmailClient.extract_body(html)
        texts = [GmailClient.extract_body(p) for p in parts]
        return "\n".join(t for t in texts if t)
