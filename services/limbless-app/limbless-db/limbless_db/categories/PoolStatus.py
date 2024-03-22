from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class PoolStatusEnum(DBEnum):
    icon: str
    description: str


class PoolStatus(ExtendedEnum[PoolStatusEnum], enum_type=PoolStatusEnum):
    DRAFT = PoolStatusEnum(0, "Draft", "✍🏼", "Plan of the pool.")
    SUBMITTED = PoolStatusEnum(1, "Submitted", "🚀", "Pool is submitted by a customer.")
    ACCEPTED = PoolStatusEnum(2, "Accepted", "📦", "Pool is accepted to be sequenced before assigned to an experiment.")
    ASSIGNED = PoolStatusEnum(3, "Assigned", "📫", "Pool is assigned to an experiment.")
    LANED = PoolStatusEnum(4, "Laned", "🚦", "Pool is assigned lane(s) from experiment.")
    LOADED = PoolStatusEnum(5, "Loaded", "🔬", "Pool is loaded on a flowcell")
    SEQUENCED = PoolStatusEnum(6, "Sequenced", "🧬", "Sequencing is finished.")
    FAILED = PoolStatusEnum(10, "Failed", "❌", "Failed")
    REJECTED = PoolStatusEnum(11, "Rejected", "⛔", "Pool was not accepted to be sequenced by staff.")
