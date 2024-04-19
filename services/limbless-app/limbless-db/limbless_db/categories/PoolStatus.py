from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class PoolStatusEnum(DBEnum):
    icon: str
    description: str


class PoolStatus(ExtendedEnum[PoolStatusEnum], enum_type=PoolStatusEnum):
    DRAFT = PoolStatusEnum(0, "Draft", "✍🏼", "Plan of the pool.")
    SUBMITTED = PoolStatusEnum(1, "Submitted", "🚀", "Pool is submitted by a customer.")
    ACCEPTED = PoolStatusEnum(2, "Accepted", "📦", "Pool is accepted and waiting to be handed over for sequencing.")
    RECEIVED = PoolStatusEnum(3, "Received", "📫", "Pool is received.")
    QCED = PoolStatusEnum(4, "QCed", "🔬", "Pool is QCed.")
    DEPLETED = PoolStatusEnum(5, "Depleted", "🧪", "Pool is depleted.")
    REJECTED = PoolStatusEnum(10, "Rejected", "⛔", "Pool was not accepted to be sequenced by staff.")
