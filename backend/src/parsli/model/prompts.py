"""Extraction prompt templates for local model inference."""

EXTRACTION_PROMPT_V1 = """\
You are a parcel-tracking assistant. Analyse the email below and extract \
shipping/delivery information. Return ONLY valid JSON matching the schema \
— no explanation, no markdown fences.

Schema:
{{
  "status": "<one of: order_confirmed | shipped | received_by_carrier | \
in_transit | arrived_in_destination_country | customs_pending | \
customs_released | handed_to_local_carrier | ready_for_pickup | \
out_for_delivery | delivered | payment_required | action_required | \
delayed_or_problem | unknown>",
  "status_confidence": <0.0–1.0>,
  "status_evidence": "<short quote ≤120 chars that justifies the status>",
  "merchant": "<store name or null>",
  "tracking_numbers": ["<tracking number>", ...],
  "order_numbers": ["<order number>", ...],
  "pickup_code": "<pickup/locker code or null>",
  "amount": <numeric customs/duty fee or null>,
  "currency": "<ISO 4217 or null>",
  "is_relevant": <true if this is a genuine shipping update, false otherwise>,
  "ignore_reason": "<why irrelevant if is_relevant=false, else null>"
}}

Important rules:
- Hebrew phrase "תודה שאספת את המשלוח" at an Israel Post branch → status: delivered
- HFD phrase "collect before" or "last day to collect" → status: action_required
- Invoices, receipts, or pure promotional emails → is_relevant: false
- Unknown status fields must remain "unknown", never guess

Email:
{email_text}
"""


def format_prompt(email_text: str, version: str = "v1") -> str:
    """Return a formatted extraction prompt for the given email text."""
    if version == "v1":
        return EXTRACTION_PROMPT_V1.format(email_text=email_text)
    raise ValueError(f"Unknown prompt version: {version}")
