from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class DeliveryStatusEnum(DBEnum):
    icon: str


class DeliveryStatus(ExtendedEnum[DeliveryStatusEnum], enum_type=DeliveryStatusEnum):
    PENDING = DeliveryStatusEnum(0, "Pending", "🕒")
    DISPATCHED = DeliveryStatusEnum(1, "Dispatched", "📬")