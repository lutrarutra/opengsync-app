from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class SampleStatusEnum(DBEnum):
    label: str
    icon: str
    description: str


class SampleStatus(ExtendedEnum):
    label: str
    icon: str
    description: str
    DRAFT = SampleStatusEnum(0, "Draft", "✍🏼", "Draft plan of the sample")
    WAITING_DELIVERY = SampleStatusEnum(1, "Waiting Delivery", "📭", "Waiting for delivery")
    STORED = SampleStatusEnum(2, "Stored", "📦", "Sample specimen was received from customer and stored")
    DEPLETED = SampleStatusEnum(10, "Depleted", "🪫", "Sample specimen was depleted")
    REJECTED = SampleStatusEnum(11, "Rejected", "⛔", "Request was rejected")

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"