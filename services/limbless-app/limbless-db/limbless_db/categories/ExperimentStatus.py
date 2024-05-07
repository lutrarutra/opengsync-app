from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class ExperimentStatusEnum(DBEnum):
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon
    

class ExperimentStatus(ExtendedEnum[ExperimentStatusEnum], enum_type=ExperimentStatusEnum):
    DRAFT = ExperimentStatusEnum(0, "Draft", "✍🏼")
    LOADED = ExperimentStatusEnum(1, "Loaded", "📦")
    SEQUENCING = ExperimentStatusEnum(2, "Sequencing", "🧬")
    FINISHED = ExperimentStatusEnum(3, "Finished", "✅")
    ARCHIVED = ExperimentStatusEnum(10, "Archived", "🗃️")
    FAILED = ExperimentStatusEnum(11, "Failed", "❌")