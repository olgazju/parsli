"""EmailCleaner — converts raw email bodies to clean, analysis-ready text.

The cleaned text is returned in a Pydantic model. It is NEVER persisted to the
database by default; only the hash and length are stored.
"""

import re

from pydantic import BaseModel

from ..languages import DEFAULT_LANGUAGES, MergedLanguageConfig, load_language_packs
from ..privacy.hashing import body_hash

# Language-agnostic patterns applied unconditionally.
_TRACKING_PIXEL = re.compile(r"https?://[^\s]+\.(gif|png|jpg)\?[^\s]+", re.IGNORECASE)
# Strip URLs from markdown links [text](url) → text, and bare https:// URLs.
# This removes URL query parameters that contain phone numbers, token IDs, and
# other non-tracking numeric sequences that pollute identifier extraction.
_MARKDOWN_URL_RE = re.compile(r"\(https?://[^\s)]+\)", re.IGNORECASE)
_BARE_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_REPEATED_WHITESPACE = re.compile(r"\n{3,}")


class CleanedEmail(BaseModel):
    email_id: str
    cleaned_text: str
    cleaned_text_hash: str
    cleaned_full_len: int
    is_shipping_shaped: bool


class EmailCleaner:
    """Cleans an email body string and returns a CleanedEmail DTO.

    Args:
        lang_config: Merged language configuration. Defaults to the bundled
                     en + he packs when omitted.
    """

    def __init__(self, lang_config: MergedLanguageConfig | None = None) -> None:
        if lang_config is None:
            lang_config = load_language_packs(DEFAULT_LANGUAGES)

        self._footer_res: list[re.Pattern[str]] = [
            re.compile(p, re.DOTALL | re.IGNORECASE)
            for p in lang_config.footer_patterns
        ]
        self._unsubscribe_res: list[re.Pattern[str]] = [
            re.compile(p, re.DOTALL | re.IGNORECASE)
            for p in lang_config.unsubscribe_patterns
        ]
        self._shipping_signal_re: re.Pattern[str] | None = (
            re.compile(
                "(?:" + "|".join(lang_config.shipping_signals) + ")",
                re.IGNORECASE,
            )
            if lang_config.shipping_signals
            else None
        )

    def clean(self, email_id: str, raw_text: str) -> CleanedEmail:
        text = self._clean(raw_text)
        return CleanedEmail(
            email_id=email_id,
            cleaned_text=text,
            cleaned_text_hash=body_hash(text),
            cleaned_full_len=len(text),
            is_shipping_shaped=self._is_shipping_shaped(text),
        )

    def _clean(self, text: str) -> str:
        text = _TRACKING_PIXEL.sub("", text)
        for pattern in self._footer_res:
            text = pattern.sub("", text)
        for pattern in self._unsubscribe_res:
            text = pattern.sub("", text)
        text = _MARKDOWN_URL_RE.sub("", text)
        text = _BARE_URL_RE.sub("", text)
        text = _REPEATED_WHITESPACE.sub("\n\n", text)
        return text.strip()

    def _is_shipping_shaped(self, text: str) -> bool:
        return self._shipping_signal_re is not None and bool(
            self._shipping_signal_re.search(text)
        )
