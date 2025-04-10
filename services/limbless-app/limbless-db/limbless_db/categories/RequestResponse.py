from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class RequestResponseEnum(DBEnum):
    icon: str

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.icon}"


class RequestResponse(ExtendedEnum[RequestResponseEnum], enum_type=RequestResponseEnum):
    ACCEPTED = RequestResponseEnum(1, "Accepted", "✅")
    PENDING_REVISION = RequestResponseEnum(2, "Pending Revision", "🔍")
    REJECTED = RequestResponseEnum(3, "Rejected", "❌")