"""DomainNormalizer — clean and validate user-supplied domain values.

Also exports SenderNormalizer for specific email address exclusions.
"""

import re
from urllib.parse import urlparse

# Minimal domain pattern: at least one label dot one label, all valid chars.
_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$")
_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


class DomainNormalizer:
    """Normalize user-supplied strings to bare lowercase domain names.

    Accepted input formats:
    - ``example.com``
    - ``@example.com``  →  ``example.com``
    - ``https://www.example.com/path``  →  ``www.example.com``
    - ``PayPal.Com``  →  ``paypal.com``
    """

    def normalize(self, value: str) -> str:
        """Return a bare lowercase domain.

        Raises:
            ValueError: If the input cannot be resolved to a valid domain.
        """
        v = value.strip()

        # Strip URL scheme + path/query — handle http://, https://, ftp:// etc.
        if "://" in v:
            parsed = urlparse(v)
            v = parsed.netloc or parsed.path

        # Strip leading @
        v = v.lstrip("@")

        # Strip port number (example.com:443 → example.com)
        v = v.split(":")[0]

        # Strip any trailing path segment that slipped through
        v = v.split("/")[0]

        v = v.lower().strip()

        if not v:
            raise ValueError(f"Cannot extract a domain from: {value!r}")

        if not _DOMAIN_RE.match(v):
            raise ValueError(
                f"Not a valid domain: {v!r} (derived from {value!r}). "
                "Expected something like 'example.com'."
            )

        return v


class SenderNormalizer:
    """Normalize a specific sender email address for exclusion rules.

    Strips display names, angle brackets, and whitespace; lowercases the result.
    Example: ``'Display Name <user@example.com>'`` → ``'user@example.com'``
    """

    def normalize(self, value: str) -> str:
        """Return a lowercase email address.

        Raises:
            ValueError: If the input cannot be resolved to a valid email address.
        """
        v = value.strip()

        # Strip display name: "Name <email>" or "<email>"
        if "<" in v and ">" in v:
            start = v.index("<") + 1
            end = v.index(">")
            v = v[start:end].strip()

        v = v.lower().strip()

        if not v:
            raise ValueError(f"Cannot extract an email address from: {value!r}")

        if not _EMAIL_RE.match(v):
            raise ValueError(
                f"Not a valid email address: {v!r} (derived from {value!r}). "
                "Expected something like 'name@example.com'."
            )

        return v
