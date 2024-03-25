from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class ExperimentStatusEnum(DBEnum):
    icon: str


class ExperimentStatus(ExtendedEnum[ExperimentStatusEnum], enum_type=ExperimentStatusEnum):
    DRAFT = ExperimentStatusEnum(0, "Draft", "✍🏼")
    POOLS_QCED = ExperimentStatusEnum(1, "Pools QCed", "🔬")
    LANED = ExperimentStatusEnum(2, "Laned", "🚦")
    LOADED = ExperimentStatusEnum(3, "Loaded", "📦")
    SEQUENCING = ExperimentStatusEnum(4, "Sequencing", "🧬")
    FINISHED = ExperimentStatusEnum(5, "Finished", "✅")
    ARCHIVED = ExperimentStatusEnum(10, "Archived", "🗃️")
    FAILED = ExperimentStatusEnum(11, "Failed", "❌")