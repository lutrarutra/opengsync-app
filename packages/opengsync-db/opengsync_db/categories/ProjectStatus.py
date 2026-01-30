from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class ProjectStatusEnum(DBEnum):
    label: str
    description: str
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"


class ProjectStatus(ExtendedEnum):
    label: str
    description: str
    icon: str

    DRAFT = ProjectStatusEnum(0, "Draft", "Project has been created but no samples have been submitted for sequencing.", "✍🏼")
    PROCESSING = ProjectStatusEnum(1, "Processing", "Project is being worked on in the lab.", "🔬")
    SEQUENCED = ProjectStatusEnum(2, "Sequenced", "All libraries are sequenced. We are working on data processing.", "🧬")
    DELIVERED = ProjectStatusEnum(3, "Delivered", "Project is completed and data is delivered.", "✅")
    ARCHIVED = ProjectStatusEnum(11, "Archived", "Data is archived.", "🗃️")