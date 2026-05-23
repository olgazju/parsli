"""Deterministic rule engine for shipping email classification and extraction.

All logic here is pure Python with no LLM involvement. Results are combined
with model output by the ExtractionOrchestrator.
"""

import re

from pydantic import BaseModel

from ..domain.identifiers import IdentifierExtractor, OrderIdentifier, TrackingIdentifier
from ..domain.statuses import ShipmentStatus
from ..languages import DEFAULT_LANGUAGES, MergedLanguageConfig, load_language_packs


class RuleExtractionResult(BaseModel):
    is_shipping_email: bool
    is_invoice: bool
    status: ShipmentStatus | None
    status_confidence: float
    status_evidence: str
    tracking_candidates: list[TrackingIdentifier]
    order_candidates: list[OrderIdentifier]
    merchant: str | None
    pickup_code: str | None
    amount: float | None
    currency: str | None


# ── Payment processor domains ─────────────────────────────────────────────────
# Emails from these senders are financial receipts, never shipment updates.
# Checked before any text rules — domain match alone is sufficient to exclude.
# Not language-specific; kept as a Python constant.
_PAYMENT_PROCESSOR_DOMAINS: frozenset[str] = frozenset({
    "payplus.co.il",
    "paypal.com",
    "stripe.com",
    "cardcom.co.il",
    "tranzila.com",
    "isracard.co.il",
})

# ── Merchant hints ────────────────────────────────────────────────────────────
# Format-based detection — not language-specific.
_MERCHANT_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("Amazon", re.compile(r"\bamazon\b", re.I)),
    ("ASOS", re.compile(r"\basos\b", re.I)),
    ("AliExpress", re.compile(r"\baliexpress\b", re.I)),
    ("Shein", re.compile(r"\bshein\b", re.I)),
    ("eBay", re.compile(r"\bebay\b", re.I)),
    ("Zara", re.compile(r"\bzara\b", re.I)),
    ("H&M", re.compile(r"\bh&m\b|\bh and m\b", re.I)),
    ("Israel Post", re.compile(r"\bisrael post\b|\bדואר ישראל\b", re.I)),
    ("HFD", re.compile(r"\bhfd\b", re.I)),
]

# ── Pickup code ───────────────────────────────────────────────────────────────
_PICKUP_CODE_RE = re.compile(
    r"(?:pickup code|collection code|locker code|code.*?pick\s*up|קוד איסוף|קוד לוקר)"
    r"[\s:]*([A-Z0-9]{4,10})",
    re.I,
)

# ── Payment amount ────────────────────────────────────────────────────────────
_AMOUNT_RE = re.compile(
    r"(?:fee|duty|pay(?:ment)?|amount|סכום|אגרה|תשלום)"
    r"(?:\s+of)?\s*[:\-]?\s*"
    r"([₪$€£]\s*\d+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?\s*(?:ILS|USD|EUR|GBP|NIS))",
    re.I,
)
_CURRENCY_MAP = {"₪": "ILS", "$": "USD", "€": "EUR", "£": "GBP", "NIS": "ILS"}

# ── Confidence values per status (engine-level, not language-specific) ─────────
_STATUS_CONF: dict[str, tuple[ShipmentStatus, float, bool]] = {
    # field_name -> (enum, confidence, needs_dotall)
    "delivered":                     (ShipmentStatus.DELIVERED, 0.95, False),
    "action_required":               (ShipmentStatus.ACTION_REQUIRED, 0.90, True),
    "ready_for_pickup":              (ShipmentStatus.READY_FOR_PICKUP, 0.93, False),
    "payment_required":              (ShipmentStatus.PAYMENT_REQUIRED, 0.92, False),
    "out_for_delivery":              (ShipmentStatus.OUT_FOR_DELIVERY, 0.92, False),
    "customs_released":              (ShipmentStatus.CUSTOMS_RELEASED, 0.88, False),
    "customs_pending":               (ShipmentStatus.CUSTOMS_PENDING, 0.85, False),
    "handed_to_local_carrier":       (ShipmentStatus.HANDED_TO_LOCAL_CARRIER, 0.82, False),
    "arrived_in_destination_country":(ShipmentStatus.ARRIVED_IN_DESTINATION_COUNTRY, 0.82, False),
    "delayed_or_problem":            (ShipmentStatus.DELAYED_OR_PROBLEM, 0.80, False),
    "in_transit":                    (ShipmentStatus.IN_TRANSIT, 0.75, False),
    "received_by_carrier":           (ShipmentStatus.RECEIVED_BY_CARRIER, 0.75, False),
    "shipped":                       (ShipmentStatus.SHIPPED, 0.80, False),
    "order_confirmed":               (ShipmentStatus.ORDER_CONFIRMED, 0.70, False),
}


def _build_status_rules(
    lang_config: MergedLanguageConfig,
) -> list[tuple[ShipmentStatus, float, re.Pattern[str]]]:
    """Compile per-status regex patterns from merged language pack phrases."""
    sp = lang_config.status_patterns
    rules: list[tuple[ShipmentStatus, float, re.Pattern[str]]] = []
    for field, (status, confidence, dotall) in _STATUS_CONF.items():
        patterns = getattr(sp, field)
        if not patterns:
            continue
        flags = re.I | (re.DOTALL if dotall else 0)
        compiled = re.compile("(?:" + "|".join(patterns) + ")", flags)
        rules.append((status, confidence, compiled))
    return rules


def _build_invoice_re(lang_config: MergedLanguageConfig) -> re.Pattern[str]:
    phrases = lang_config.billing_exclusion_phrases
    return re.compile("(?:" + "|".join(phrases) + ")", re.I) if phrases else re.compile(r"(?!)")


def _build_invoice_negative_re(lang_config: MergedLanguageConfig) -> re.Pattern[str]:
    phrases = lang_config.shipping_override_phrases
    return re.compile("(?:" + "|".join(phrases) + ")", re.I) if phrases else re.compile(r"(?!)")


class RuleEngine:
    """Applies deterministic rules to cleaned email text.

    Args:
        lang_config: Merged language configuration. Defaults to the bundled
                     en + he packs when omitted.
    """

    def __init__(self, lang_config: MergedLanguageConfig | None = None) -> None:
        if lang_config is None:
            lang_config = load_language_packs(DEFAULT_LANGUAGES)
        self._invoice_re = _build_invoice_re(lang_config)
        self._invoice_negative_re = _build_invoice_negative_re(lang_config)
        self._status_rules = _build_status_rules(lang_config)
        self._extractor = IdentifierExtractor(lang_config)

    def extract(
        self,
        email_id: str,  # noqa: ARG002
        cleaned_text: str,
        sender_domain: str | None = None,
        subject: str = "",
    ) -> RuleExtractionResult:
        # Payment processor domains are financial emails — never shipment updates.
        if sender_domain and sender_domain.lower() in _PAYMENT_PROCESSOR_DOMAINS:
            return self._invoice_result()

        text = cleaned_text
        # Prepend subject so identifier patterns also run against it. Status
        # matching uses only the body to avoid subject-line false positives.
        id_text = f"{subject}\n{text}" if subject else text

        is_invoice = self._detect_invoice(text)
        status, confidence, evidence = self._detect_status(subject, id_text)
        merchant = self._detect_merchant(text)
        pickup_code = self._detect_pickup_code(text)
        amount, currency = self._detect_amount(text)
        tracking = self._extractor.extract_tracking_candidates(id_text)
        orders = self._extractor.extract_order_candidates(id_text)

        # Remove tracking candidates that are explicitly labeled as order numbers.
        _order_values: set[str] = {o.value for o in orders}
        tracking = [t for t in tracking if t.value not in _order_values]

        is_shipping = (bool(status) or bool(tracking)) and not is_invoice

        return RuleExtractionResult(
            is_shipping_email=is_shipping,
            is_invoice=is_invoice,
            status=status,
            status_confidence=confidence,
            status_evidence=evidence,
            tracking_candidates=tracking,
            order_candidates=orders,
            merchant=merchant,
            pickup_code=pickup_code,
            amount=amount,
            currency=currency,
        )

    def _detect_invoice(self, text: str) -> bool:
        return bool(self._invoice_re.search(text)) and not bool(
            self._invoice_negative_re.search(text)
        )

    def _detect_status(
        self,
        subject: str,
        id_text: str,
    ) -> tuple[ShipmentStatus | None, float, str]:
        # "Ordered: <product>" subjects mean ORDER_CONFIRMED regardless of body content.
        # Amazon (and some other retailers) include a full delivery-step progress bar
        # ("Ordered  Shipped  Out for delivery  Delivered") in every email body, which
        # would otherwise match out_for_delivery even for a freshly placed order.
        if subject and re.match(r"^Ordered\s*:", subject.strip(), re.IGNORECASE):
            return ShipmentStatus.ORDER_CONFIRMED, 0.85, subject[:120].strip()
        # "New Order #..." subjects indicate a freshly placed order. Without this
        # override, body text such as "will be shipped soon" triggers SHIPPED.
        if subject and re.match(r"^New\s+Order\b", subject.strip(), re.IGNORECASE):
            return ShipmentStatus.ORDER_CONFIRMED, 0.85, subject[:120].strip()
        return self._match_status(id_text)

    def _match_status(
        self,
        text: str,
    ) -> tuple[ShipmentStatus | None, float, str]:
        for status, confidence, pattern in self._status_rules:
            match = pattern.search(text)
            if match:
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 60)
                evidence = text[start:end].replace("\n", " ").strip()
                return status, confidence, evidence
        return None, 0.0, ""

    @staticmethod
    def _detect_merchant(text: str) -> str | None:
        for name, pattern in _MERCHANT_HINTS:
            if pattern.search(text):
                return name
        return None

    @staticmethod
    def _detect_pickup_code(text: str) -> str | None:
        match = _PICKUP_CODE_RE.search(text)
        return match.group(1).upper() if match else None

    @staticmethod
    def _detect_amount(text: str) -> tuple[float | None, str | None]:
        match = _AMOUNT_RE.search(text)
        if not match:
            return None, None
        raw = match.group(1).strip()
        currency: str | None = None
        for symbol, code in _CURRENCY_MAP.items():
            if symbol in raw:
                currency = code
                raw = raw.replace(symbol, "").strip()
                break
        for code in ("ILS", "USD", "EUR", "GBP", "NIS"):
            if raw.upper().endswith(code):
                currency = "ILS" if code == "NIS" else code
                raw = raw[: -len(code)].strip()
                break
        try:
            amount = float(raw.replace(",", "."))
        except ValueError:
            return None, None
        return amount, currency

    def _invoice_result(self) -> RuleExtractionResult:
        return RuleExtractionResult(
            is_shipping_email=False,
            is_invoice=True,
            status=None,
            status_confidence=0.0,
            status_evidence="",
            tracking_candidates=[],
            order_candidates=[],
            merchant=None,
            pickup_code=None,
            amount=None,
            currency=None,
        )
