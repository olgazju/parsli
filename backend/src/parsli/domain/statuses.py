from enum import Enum


class ShipmentStatus(str, Enum):
    ORDER_CONFIRMED = "order_confirmed"
    SHIPPED = "shipped"
    RECEIVED_BY_CARRIER = "received_by_carrier"
    IN_TRANSIT = "in_transit"
    ARRIVED_IN_DESTINATION_COUNTRY = "arrived_in_destination_country"
    CUSTOMS_PENDING = "customs_pending"
    CUSTOMS_RELEASED = "customs_released"
    HANDED_TO_LOCAL_CARRIER = "handed_to_local_carrier"
    READY_FOR_PICKUP = "ready_for_pickup"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    PAYMENT_REQUIRED = "payment_required"
    ACTION_REQUIRED = "action_required"
    DELAYED_OR_PROBLEM = "delayed_or_problem"
    UNKNOWN = "unknown"


TERMINAL_STATUSES: frozenset[ShipmentStatus] = frozenset({ShipmentStatus.DELIVERED})

# Side statuses do not participate in linear chronology ordering — they never
# create "impossible sequence" conflicts.
SIDE_STATUSES: frozenset[ShipmentStatus] = frozenset({
    ShipmentStatus.ACTION_REQUIRED,
    ShipmentStatus.PAYMENT_REQUIRED,
    ShipmentStatus.DELAYED_OR_PROBLEM,
    ShipmentStatus.UNKNOWN,
})

MAIN_STATUS_ORDER: list[ShipmentStatus] = [
    ShipmentStatus.ORDER_CONFIRMED,
    ShipmentStatus.SHIPPED,
    ShipmentStatus.RECEIVED_BY_CARRIER,
    ShipmentStatus.IN_TRANSIT,
    ShipmentStatus.ARRIVED_IN_DESTINATION_COUNTRY,
    ShipmentStatus.CUSTOMS_PENDING,
    ShipmentStatus.CUSTOMS_RELEASED,
    ShipmentStatus.HANDED_TO_LOCAL_CARRIER,
    ShipmentStatus.READY_FOR_PICKUP,
    ShipmentStatus.OUT_FOR_DELIVERY,
    ShipmentStatus.DELIVERED,
]

_MAIN_STATUS_RANK: dict[ShipmentStatus, int] = {
    s: i for i, s in enumerate(MAIN_STATUS_ORDER)
}

STATUS_LABELS: dict[ShipmentStatus, str] = {
    ShipmentStatus.ORDER_CONFIRMED: "Order Confirmed",
    ShipmentStatus.SHIPPED: "Shipped",
    ShipmentStatus.RECEIVED_BY_CARRIER: "Received by Carrier",
    ShipmentStatus.IN_TRANSIT: "In Transit",
    ShipmentStatus.ARRIVED_IN_DESTINATION_COUNTRY: "Arrived in Destination Country",
    ShipmentStatus.CUSTOMS_PENDING: "Pending Customs Clearance",
    ShipmentStatus.CUSTOMS_RELEASED: "Released from Customs",
    ShipmentStatus.HANDED_TO_LOCAL_CARRIER: "Handed to Local Carrier",
    ShipmentStatus.READY_FOR_PICKUP: "Ready for Pickup",
    ShipmentStatus.OUT_FOR_DELIVERY: "Out for Delivery",
    ShipmentStatus.DELIVERED: "Delivered",
    ShipmentStatus.PAYMENT_REQUIRED: "Payment Required",
    ShipmentStatus.ACTION_REQUIRED: "Action Required",
    ShipmentStatus.DELAYED_OR_PROBLEM: "Delayed or Problem",
    ShipmentStatus.UNKNOWN: "Unknown",
}


def status_rank(status: ShipmentStatus) -> int | None:
    """Return the linear rank of a main status, or None for side statuses."""
    return _MAIN_STATUS_RANK.get(status)
