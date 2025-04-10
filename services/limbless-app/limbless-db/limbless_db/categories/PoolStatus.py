from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class PoolStatusEnum(DBEnum):
    icon: str
    description: str

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.name} {self.icon}"


class PoolStatus(ExtendedEnum[PoolStatusEnum], enum_type=PoolStatusEnum):
    DRAFT = PoolStatusEnum(0, "Draft", "✍🏼", "Draft plan of the pool")
    SUBMITTED = PoolStatusEnum(1, "Submitted", "🚀", "Pool is submitted for review by a customer")
    ACCEPTED = PoolStatusEnum(2, "Accepted", "✅", "Pool is accepted and waiting to be handed over for sequencing")
    STORED = PoolStatusEnum(3, "Stored", "📦", "Pool is stored and ready for sequencing")
    SEQUENCED = PoolStatusEnum(4, "Sequenced", "🏁", "Pool is sequenced")
    REJECTED = PoolStatusEnum(10, "Rejected", "⛔", "Pool was not accepted to be sequenced by staff")
    ARCHIVED = PoolStatusEnum(11, "Archived", "🗃️", "Pool is sequenced and the data is archived")
