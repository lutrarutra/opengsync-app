from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SampleStatusEnum(DBEnum):
    icon: str
    description: str

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.name} {self.icon}"


class SampleStatus(ExtendedEnum[SampleStatusEnum], enum_type=SampleStatusEnum):
    DRAFT = SampleStatusEnum(0, "Draft", "✍🏼", "Draft plan of the sample")
    WAITING_DELIVERY = SampleStatusEnum(1, "Waiting Delivery", "📭", "Waiting for delivery")
    STORED = SampleStatusEnum(2, "Stored", "📦", "Sample specimen was received from customer and stored")
    DEPLETED = SampleStatusEnum(10, "Depleted", "🪫", "Sample specimen was depleted")
    REJECTED = SampleStatusEnum(11, "Rejected", "⛔", "Request was rejected")