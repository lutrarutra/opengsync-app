from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class RequestResponseEnum(DBEnum):
    icon: str


class RequestResponse(ExtendedEnum[RequestResponseEnum], enum_type=RequestResponseEnum):
    ACCEPTED = RequestResponseEnum(1, "Accepted", "✅")
    PENDING_REVISION = RequestResponseEnum(2, "Pending Revision", "🔍")
    REJECTED = RequestResponseEnum(3, "Rejected", "❌")