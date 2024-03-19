from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class PoolStatusEnum(DBEnum):
    icon: str


class PoolStatus(ExtendedEnum[PoolStatusEnum], enum_type=PoolStatusEnum):
    DRAFT = PoolStatusEnum(0, "Draft", "✍🏼")
    SUBMITTED = PoolStatusEnum(1, "Submitted", "🚀")
    ACCEPTED = PoolStatusEnum(2, "Accepted", "📦")
    ASSIGNED = PoolStatusEnum(3, "Assigned", "📫")
    LANED = PoolStatusEnum(4, "Laned", "🔬")
    SEQUENCED = PoolStatusEnum(5, "Sequenced", "🧬")
    FAILED = PoolStatusEnum(10, "Failed", "❌")
    REJECTED = PoolStatusEnum(11, "Rejected", "⛔")
