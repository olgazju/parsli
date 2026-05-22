"""EmailCleaner — converts raw email bodies to clean, analysis-ready text.

The cleaned text is returned in a Pydantic model. It is NEVER persisted to the
database by default; only the hash and length are stored.
"""

import re

from pydantic import BaseModel

from ..privacy.hashing import body_hash


# Boilerplate patterns that add noise without useful signals.
_UNSUBSCRIBE_RE = re.compile(
    r"(?:unsubscribe|הסר\s*מרשימה|בטל\s*מנוי|to stop receiving|manage your preferences)"
    r".{0,200}",
    re.IGNORECASE | re.DOTALL,
)
_LEGAL_FOOTER_RE = re.compile(
    r"(?:this email was sent|if you have received this|confidentiality notice|"
    r"all rights reserved|©\s*\d{4}|privacy policy|terms of service)"
    r".{0,500}",
    re.IGNORECASE | re.DOTALL,
)
_REPEATED_WHITESPACE = re.compile(r"\n{3,}")
_TRACKING_PIXEL = re.compile(r"https?://[^\s]+\.(gif|png|jpg)\?[^\s]+", re.IGNORECASE)


class CleanedEmail(BaseModel):
    email_id: str
    cleaned_text: str
    cleaned_text_hash: str
    cleaned_full_len: int
    is_shipping_shaped: bool


# Signals that strongly suggest this is a shipping/delivery email.
_SHIPPING_SIGNALS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:tracking|shipment|delivery|dispatch|courier|customs|parcel)\b", re.I),
    re.compile(r"\b(?:out for delivery|ready for pickup|has been delivered|been shipped)\b", re.I),
    # Hebrew signals
    re.compile(r"(?:משלוח|חבילה|מעקב|נשלח|מוכן לאיסוף|יצא לחלוקה|נמסר)", re.I),
]


class EmailCleaner:
    """Cleans an email body string and returns a CleanedEmail DTO."""

    def clean(self, email_id: str, raw_text: str) -> CleanedEmail:
        text = self._clean(raw_text)
        return CleanedEmail(
            email_id=email_id,
            cleaned_text=text,
            cleaned_text_hash=body_hash(text),
            cleaned_full_len=len(text),
            is_shipping_shaped=self._is_shipping_shaped(text),
        )

    @staticmethod
    def _clean(text: str) -> str:
        text = _TRACKING_PIXEL.sub("", text)
        text = _UNSUBSCRIBE_RE.sub("", text)
        text = _LEGAL_FOOTER_RE.sub("", text)
        text = _REPEATED_WHITESPACE.sub("\n\n", text)
        return text.strip()

    @staticmethod
    def _is_shipping_shaped(text: str) -> bool:
        return any(p.search(text) for p in _SHIPPING_SIGNALS)
