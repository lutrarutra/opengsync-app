from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class ExperimentStatusEnum(DBEnum):
    icon: str
    description: str

    @property
    def select_name(self) -> str:
        return self.icon


class ExperimentStatus(ExtendedEnum[ExperimentStatusEnum], enum_type=ExperimentStatusEnum):
    DRAFT = ExperimentStatusEnum(0, "Draft", "✍🏼", "Draft plan of the experiment")
    LOADED = ExperimentStatusEnum(1, "Loaded", "⚙️", "Libraries are loaded on the flowcell")
    SEQUENCING = ExperimentStatusEnum(2, "Sequencing", "🧬", "Sequencing")
    SEQUENCED = ExperimentStatusEnum(3, "Sequenced", "✅", "Sequencing is finished")
    DEMULTIPLEXED = ExperimentStatusEnum(4, "Demultiplexed", "📊", "Data is demultiplexed and ready for analysis")
    ARCHIVED = ExperimentStatusEnum(10, "Archived", "🗃️", "Data is archived")
    FAILED = ExperimentStatusEnum(11, "Failed", "❌", "Sequencing failed")