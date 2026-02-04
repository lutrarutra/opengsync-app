from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class RequestResponseEnum(DBEnum):
    label: str
    icon: str


class RequestResponse(ExtendedEnum):
    label: str
    icon: str
    ACCEPTED = RequestResponseEnum(1, "Accepted", "✅")
    PENDING_REVISION = RequestResponseEnum(2, "Pending Revision", "🔍")
    REJECTED = RequestResponseEnum(3, "Rejected", "❌")

    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"