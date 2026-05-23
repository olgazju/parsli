"""Prompt templates for local model inference.

Two modes:
  required — full classification + extraction. Used when rules are weak or
             missing important information.
  audit    — lightweight agreement check. Used when rules already produced a
             confident classification and the model is only validating it.
"""

# ── Required prompt (full classification) ─────────────────────────────────────

_REQUIRED_SYSTEM = """\
You are a parcel-tracking assistant. Analyse the email below and classify it. \
Return ONLY valid JSON matching the schema — no explanation, no markdown fences.

Schema:
{{
  "email_type": "<one of: order_confirmation | shipping_update | pickup_ready | \
delivered | payment_problem | billing_only | non_shipping | digital_product>",
  "status": "<one of: order_confirmed | shipped | received_by_carrier | \
in_transit | arrived_in_destination_country | customs_pending | \
customs_released | handed_to_local_carrier | ready_for_pickup | \
out_for_delivery | delivered | payment_required | action_required | \
delayed_or_problem | unknown>",
  "status_confidence": <0.0–1.0>,
  "status_evidence": "<short quote ≤120 chars that justifies the status>",
  "merchant": "<store name or null>",
  "carrier": "<carrier name or null, e.g. 'Israel Post', 'DHL', 'HFD'>",
  "tracking_numbers": ["<tracking number>", ...],
  "order_numbers": ["<order number>", ...],
  "pickup_code": "<pickup/locker code or null>",
  "amount": <numeric customs/duty fee or null>,
  "currency": "<ISO 4217 or null>",
  "reasoning": "<one sentence explaining the classification decision>"
}}

email_type rules:
- order_confirmation: order placed, not yet shipped
- shipping_update: carrier has the parcel, in transit, customs, out for delivery
- pickup_ready: parcel waiting at branch/locker for collection (including HFD alerts)
- delivered: parcel confirmed delivered or collected
- payment_problem: customs duty or payment required to release parcel
- billing_only: invoice, receipt, account statement — no physical shipment involved
- non_shipping: unrelated email
- digital_product: SaaS, ebook, software licence, download — not a physical parcel

Important rules:
- Hebrew "תודה שאספת את המשלוח" at Israel Post → email_type: delivered, status: delivered
- HFD "collect before" / "last day to collect" → email_type: pickup_ready, status: action_required
- Invoices, receipts, periodic billing → email_type: billing_only, status: unknown
- SaaS or downloadable products → email_type: digital_product, status: unknown
- If status is unknown, status_confidence must be 0.0
- Never guess tracking numbers — only extract numbers explicitly labelled as tracking IDs"""

_REQUIRED_EMAIL_BLOCK = """\

Subject: {subject}
Sender: {sender_domain}

{email_text}"""


# ── Audit prompt (lightweight validation) ─────────────────────────────────────

_AUDIT_SYSTEM = """\
You are a parcel-tracking assistant validating a rule-based classification. \
Return ONLY valid JSON matching the schema — no explanation, no markdown fences.

Schema:
{{
  "agrees": <true if you agree with the rule classification, false if not>,
  "email_type": "<your email_type — echo the rule value if you agree>",
  "status": "<your status — echo the rule value if you agree>",
  "status_confidence": <0.0–1.0, your confidence>,
  "reason": "<one sentence explaining disagreement, or null if you agree>"
}}

email_type values: order_confirmation | shipping_update | pickup_ready | \
delivered | payment_problem | billing_only | non_shipping | digital_product

status values: order_confirmed | shipped | received_by_carrier | in_transit | \
arrived_in_destination_country | customs_pending | customs_released | \
handed_to_local_carrier | ready_for_pickup | out_for_delivery | delivered | \
payment_required | action_required | delayed_or_problem | unknown

Instructions:
- If you agree, set agrees=true and echo the rule email_type/status in your response.
- If you disagree, set agrees=false and provide corrected email_type/status and a brief reason.
- Never guess — only correct when you are confident the rules are wrong."""

_AUDIT_RULE_BLOCK = """\

Rules classified this email as:
  email_type:  {rule_email_type}
  status:      {rule_status}
  confidence:  {rule_confidence:.2f}
  evidence:    "{rule_evidence}"
  tracking:    {tracking}
  orders:      {orders}

Email context:
  Subject:  {subject}
  Sender:   {sender_domain}
  Preview:  {preview}"""


def build_model_text_preview(cleaned_text: str, max_chars: int = 4000) -> str:
    """Clip cleaned text to a size suitable for model input.

    Args:
        cleaned_text: Fully cleaned email body.
        max_chars: Maximum number of characters to return.

    Returns:
        Clipped text, at most max_chars characters.
    """
    return cleaned_text[:max_chars]


def format_required_prompt(
    subject: str,
    sender_domain: str | None,
    email_text: str,
) -> str:
    """Format the full extraction prompt for MODEL_REQUIRED mode.

    Args:
        subject: Email subject line.
        sender_domain: Sender domain (e.g. 'amazon.com'), or None.
        email_text: Cleaned, clipped email body.

    Returns:
        Ready-to-send prompt string.
    """
    email_block = _REQUIRED_EMAIL_BLOCK.format(
        subject=subject or "",
        sender_domain=sender_domain or "unknown",
        email_text=email_text,
    )
    return _REQUIRED_SYSTEM + email_block


def format_audit_prompt(
    subject: str,
    sender_domain: str | None,
    preview: str,
    rule_email_type: str,
    rule_status: str,
    rule_confidence: float,
    rule_evidence: str,
    tracking_candidates: list[str],
    order_candidates: list[str],
) -> str:
    """Format the lightweight validation prompt for MODEL_AUDIT mode.

    Args:
        subject: Email subject line.
        sender_domain: Sender domain, or None.
        preview: Short cleaned-text preview (audit_max_chars characters).
        rule_email_type: Email type string from rules (e.g. 'shipping_update').
        rule_status: Status string from rules (e.g. 'in_transit'), or 'none'.
        rule_confidence: Rule confidence score (0.0–1.0).
        rule_evidence: Short evidence snippet from rules.
        tracking_candidates: List of tracking number strings extracted by rules.
        order_candidates: List of order number strings extracted by rules.

    Returns:
        Ready-to-send prompt string.
    """
    tracking_str = ", ".join(tracking_candidates) if tracking_candidates else "none"
    orders_str = ", ".join(order_candidates) if order_candidates else "none"
    rule_block = _AUDIT_RULE_BLOCK.format(
        rule_email_type=rule_email_type,
        rule_status=rule_status,
        rule_confidence=rule_confidence,
        rule_evidence=rule_evidence or "",
        tracking=tracking_str,
        orders=orders_str,
        subject=subject or "",
        sender_domain=sender_domain or "unknown",
        preview=preview,
    )
    return _AUDIT_SYSTEM + rule_block
