from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class ExperimentStatusEnum(DBEnum):
    icon: str


class ExperimentStatus(ExtendedEnum[ExperimentStatusEnum], enum_type=ExperimentStatusEnum):
    DRAFT = ExperimentStatusEnum(0, "Draft", "✍🏼")
    SEQUENCING = ExperimentStatusEnum(1, "Sequencing", "🧬")
    FINISHED = ExperimentStatusEnum(2, "Finished", "✅")
    ARCHIVED = ExperimentStatusEnum(3, "Archived", "🗃️")
    FAILED = ExperimentStatusEnum(4, "Failed", "❌")