"""EmailType — coarse category assigned to each email before shipment resolution.

Separate from ShipmentStatus: EmailType describes what kind of email this is,
while ShipmentStatus describes the physical state of the parcel.
"""

from enum import Enum

from .statuses import ShipmentStatus


class EmailType(str, Enum):
    ORDER_CONFIRMATION = "order_confirmation"
    SHIPPING_UPDATE = "shipping_update"
    PICKUP_READY = "pickup_ready"
    DELIVERED = "delivered"
    PAYMENT_PROBLEM = "payment_problem"
    BILLING_ONLY = "billing_only"
    NON_SHIPPING = "non_shipping"
    DIGITAL_PRODUCT = "digital_product"


_STATUS_TO_EMAIL_TYPE: dict[ShipmentStatus, "EmailType"] = {
    ShipmentStatus.ORDER_CONFIRMED: EmailType.ORDER_CONFIRMATION,
    ShipmentStatus.SHIPPED: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.RECEIVED_BY_CARRIER: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.IN_TRANSIT: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.ARRIVED_IN_DESTINATION_COUNTRY: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.CUSTOMS_PENDING: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.CUSTOMS_RELEASED: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.HANDED_TO_LOCAL_CARRIER: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.READY_FOR_PICKUP: EmailType.PICKUP_READY,
    ShipmentStatus.OUT_FOR_DELIVERY: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.DELIVERED: EmailType.DELIVERED,
    ShipmentStatus.PAYMENT_REQUIRED: EmailType.PAYMENT_PROBLEM,
    # ACTION_REQUIRED is the "collect before it's returned" HFD case → pickup
    ShipmentStatus.ACTION_REQUIRED: EmailType.PICKUP_READY,
    ShipmentStatus.DELAYED_OR_PROBLEM: EmailType.SHIPPING_UPDATE,
    ShipmentStatus.UNKNOWN: EmailType.NON_SHIPPING,
}


def email_type_from_status(
    status: ShipmentStatus | None,
    is_invoice: bool,
) -> EmailType:
    """Derive a coarse EmailType from the deterministic rule outputs.

    Args:
        status: The ShipmentStatus matched by the rule engine, or None.
        is_invoice: Whether the rule engine flagged this as a billing email.

    Returns:
        The best-fit EmailType. Billing takes priority over status mapping.
    """
    if is_invoice:
        return EmailType.BILLING_ONLY
    if status is None:
        return EmailType.NON_SHIPPING
    return _STATUS_TO_EMAIL_TYPE.get(status, EmailType.NON_SHIPPING)
