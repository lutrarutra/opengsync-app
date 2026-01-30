from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class DeliveryStatusEnum(DBEnum):
    label: str
    icon: str

    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"

class DeliveryStatus(ExtendedEnum):
    label: str
    icon: str
    
    PENDING = DeliveryStatusEnum(0, "Pending", "🕒")
    DISPATCHED = DeliveryStatusEnum(1, "Dispatched", "📬")