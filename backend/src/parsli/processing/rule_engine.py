"""Deterministic rule engine for shipping email classification and extraction.

All logic here is pure Python with no LLM involvement. Results are combined
with model output by the ExtractionOrchestrator.
"""

import re

from pydantic import BaseModel

from ..domain.identifiers import (
    OrderIdentifier,
    TrackingIdentifier,
    extract_order_candidates,
    extract_tracking_candidates,
)
from ..domain.statuses import ShipmentStatus


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


# ── Status phrase tables ───────────────────────────────────────────────────────

# Each entry: (status, confidence, phrase_pattern)
# Listed most-specific first — first match wins.
_STATUS_RULES: list[tuple[ShipmentStatus, float, re.Pattern[str]]] = [
    # ── Delivered ─────────────────────────────────────────────────────────────
    (
        ShipmentStatus.DELIVERED,
        0.95,
        re.compile(
            r"(?:has been delivered|was delivered|successfully delivered|"
            r"delivery complete|your order has been delivered|"
            # Hebrew Israel Post pickup confirmation
            r"תודה שאספת את המשלוח|נאסף בהצלחה|המשלוח נמסר|נמסר ללקוח|"
            r"הגיע ליעדו|נמסר בהצלחה)",
            re.I,
        ),
    ),
    # ── Action required (HFD + generic) — checked BEFORE ready_for_pickup ──────
    # "collect before ... will be returned" is more urgent than plain pickup notice.
    (
        ShipmentStatus.ACTION_REQUIRED,
        0.90,
        re.compile(
            r"(?:collect before|last day to collect|return deadline|action required|"
            r"will be returned|אסוף לפני|יום אחרון לאיסוף|הזמנה תוחזר|"
            r"collect.*?before.*?return|אנא אסוף את הזמנתך)",
            re.I | re.DOTALL,
        ),
    ),
    # ── Ready for pickup ──────────────────────────────────────────────────────
    (
        ShipmentStatus.READY_FOR_PICKUP,
        0.93,
        re.compile(
            r"(?:ready for (?:pickup|collection)|available for collection|"
            r"pick up your|collect your (?:parcel|package)|"
            r"מוכן לאיסוף|ממתין לאיסוף|ניתן לאסוף|זמין לאיסוף)",
            re.I,
        ),
    ),
    # ── Payment / customs duty required ───────────────────────────────────────
    (
        ShipmentStatus.PAYMENT_REQUIRED,
        0.92,
        re.compile(
            r"(?:customs duty|import duty|customs fee|pay.*?(?:customs|duty|fee)|"
            r"payment required|fee of|אגרת מכס|תשלום מכס|נדרש תשלום|שלם מכס)",
            re.I,
        ),
    ),
    # ── Out for delivery ──────────────────────────────────────────────────────
    (
        ShipmentStatus.OUT_FOR_DELIVERY,
        0.92,
        re.compile(
            r"(?:out for delivery|on its way to you|with our delivery driver|"
            r"יצא לחלוקה|בדרך אליך|שליח בדרך)",
            re.I,
        ),
    ),
    # ── Customs released ──────────────────────────────────────────────────────
    (
        ShipmentStatus.CUSTOMS_RELEASED,
        0.88,
        re.compile(
            r"(?:cleared customs|released from customs|customs clearance complete|"
            r"שוחרר מהמכס|עבר את המכס|מכס שוחרר)",
            re.I,
        ),
    ),
    # ── Customs pending ───────────────────────────────────────────────────────
    (
        ShipmentStatus.CUSTOMS_PENDING,
        0.85,
        re.compile(
            r"(?:held at customs|pending customs|customs inspection|awaiting customs|"
            r"עצור במכס|ממתין למכס|בהמתנה למכס|בביקורת מכס)",
            re.I,
        ),
    ),
    # ── Handed to local carrier ───────────────────────────────────────────────
    (
        ShipmentStatus.HANDED_TO_LOCAL_CARRIER,
        0.82,
        re.compile(
            r"(?:handed to|transferred to|passed to|local carrier|last mile|"
            r"הועבר לחברה מקומית|הועבר לשליח|מסור לחברת משלוחים)",
            re.I,
        ),
    ),
    # ── Arrived in destination country ───────────────────────────────────────
    (
        ShipmentStatus.ARRIVED_IN_DESTINATION_COUNTRY,
        0.82,
        re.compile(
            r"(?:arrived in|has arrived in|entered.*?country|"
            r"הגיע לישראל|נכנס למדינה|הגיע ליעד)",
            re.I,
        ),
    ),
    # ── Delayed / problem ─────────────────────────────────────────────────────
    (
        ShipmentStatus.DELAYED_OR_PROBLEM,
        0.80,
        re.compile(
            r"(?:delayed|delay|cannot be delivered|delivery attempt failed|"
            r"delivery exception|undeliverable|address not found|"
            r"עיכוב|לא ניתן למסור|כתובת שגויה|בעיית מסירה)",
            re.I,
        ),
    ),
    # ── In transit ────────────────────────────────────────────────────────────
    (
        ShipmentStatus.IN_TRANSIT,
        0.75,
        re.compile(
            r"(?:in transit|on its way|in delivery|en route|"
            r"בדרך|בתעבורה|בנסיעה|בטיסה|בספינה)",
            re.I,
        ),
    ),
    # ── Received by carrier ───────────────────────────────────────────────────
    (
        ShipmentStatus.RECEIVED_BY_CARRIER,
        0.75,
        re.compile(
            r"(?:received by carrier|picked up by|accepted by|collected by carrier|"
            r"נאסף ע.*?י|התקבל אצל השליח|התקבל לטיפול)",
            re.I,
        ),
    ),
    # ── Shipped ───────────────────────────────────────────────────────────────
    (
        ShipmentStatus.SHIPPED,
        0.80,
        re.compile(
            r"(?:has shipped|has been shipped|is on its way|dispatched|"
            r"your order.*?ship|item.*?shipped|נשלח|יצא לדרך|שוגר)",
            re.I,
        ),
    ),
    # ── Order confirmed ───────────────────────────────────────────────────────
    (
        ShipmentStatus.ORDER_CONFIRMED,
        0.70,
        re.compile(
            r"(?:order confirmed|order received|thank you for your order|"
            r"order.*?placed|הזמנה אושרה|הזמנתך התקבלה|תודה על הזמנתך)",
            re.I,
        ),
    ),
]

# ── Payment processor domains ─────────────────────────────────────────────────
# Emails from these senders are financial receipts, never shipment updates.
# Checked before any text rules — domain match alone is sufficient to exclude.

_PAYMENT_PROCESSOR_DOMAINS: frozenset[str] = frozenset({
    "payplus.co.il",
    "paypal.com",
    "stripe.com",
    "cardcom.co.il",
    "tranzila.com",
    "isracard.co.il",
})

# ── Invoice / non-shipment signals ────────────────────────────────────────────

_INVOICE_RE = re.compile(
    r"(?:invoice|receipt|חשבונית|קבלה|billing statement|your statement|"
    r"payment confirmation|account statement)",
    re.I,
)
_INVOICE_NEGATIVE_RE = re.compile(
    r"(?:tracking|shipment|delivery|shipped|dispatch)",
    re.I,
)

# ── Merchant hints ────────────────────────────────────────────────────────────

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


_INVOICE_RESULT = RuleExtractionResult(
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


class RuleEngine:
    """Applies deterministic rules to cleaned email text."""

    def extract(
        self,
        email_id: str,  # noqa: ARG002
        cleaned_text: str,
        sender_domain: str | None = None,
    ) -> RuleExtractionResult:
        # Payment processor domains are financial emails — never shipment updates.
        if sender_domain and sender_domain.lower() in _PAYMENT_PROCESSOR_DOMAINS:
            return _INVOICE_RESULT

        text = cleaned_text

        is_invoice = self._detect_invoice(text)
        status, confidence, evidence = self._match_status(text)
        merchant = self._detect_merchant(text)
        pickup_code = self._detect_pickup_code(text)
        amount, currency = self._detect_amount(text)
        tracking = extract_tracking_candidates(text)
        orders = extract_order_candidates(text)

        is_shipping = bool(status) and not is_invoice

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

    @staticmethod
    def _detect_invoice(text: str) -> bool:
        return bool(_INVOICE_RE.search(text)) and not bool(_INVOICE_NEGATIVE_RE.search(text))

    @staticmethod
    def _match_status(
        text: str,
    ) -> tuple[ShipmentStatus | None, float, str]:
        for status, confidence, pattern in _STATUS_RULES:
            match = pattern.search(text)
            if match:
                # Extract a short evidence snippet centred on the match
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
