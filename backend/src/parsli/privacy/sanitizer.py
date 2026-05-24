import re

# Ordered from most-specific to least-specific to avoid partial replacements.
_EMAIL_ADDR = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_DISPLAY_NAME = re.compile(r'^"?([^"<@\n]+?)"?\s*<[^>]+>$')
_IL_PHONE = re.compile(r"\b0\d{1,2}[\-\s]?\d{7}\b")
_INTL_PHONE = re.compile(r"\b(?:\+\d{1,3}[\s\-]?)?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,5}\b")
_CREDIT_CARD = re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b")
_IL_ADDRESS = re.compile(
    r"\b\d{1,5}\s+[A-Za-zא-ת][A-Za-zא-ת\s]{5,40}"
    r"(?:street|st|avenue|ave|road|rd|blvd|drive|dr|רחוב|שדרות|דרך)\b",
    re.IGNORECASE,
)


def redact_pii(text: str) -> str:
    """Replace PII patterns with generic placeholder tokens."""
    text = _EMAIL_ADDR.sub("[EMAIL]", text)
    text = _IL_PHONE.sub("[PHONE]", text)
    text = _INTL_PHONE.sub("[PHONE]", text)
    text = _CREDIT_CARD.sub("[CARD]", text)
    text = _IL_ADDRESS.sub("[ADDRESS]", text)
    return text


def extract_sender_domain(sender_header: str) -> str | None:
    """Extract domain from a From header value like 'Name <user@domain.com>'."""
    match = _EMAIL_ADDR.search(sender_header)
    if not match:
        return None
    parts = match.group(0).split("@")
    if len(parts) == 2:
        return parts[1].lower().strip()
    return None


def extract_sender_display_name(sender_header: str) -> str | None:
    """Extract the display name from a From header like 'Name <user@domain.com>'.

    Returns None when the header is bare (just an email address) or empty.
    Strips surrounding quotes and whitespace.
    """
    m = _DISPLAY_NAME.match(sender_header.strip())
    if not m:
        return None
    name = m.group(1).strip().strip('"').strip()
    return name or None


def clip_text(text: str, max_chars: int) -> str:
    """Clip text to at most max_chars, preferring a word boundary."""
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    last_space = clipped.rfind(" ")
    if last_space > max_chars - 60:
        return clipped[:last_space] + "…"
    return clipped + "…"
