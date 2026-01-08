from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class TaskStatusEnum(DBEnum):
    description: str
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.name} {self.icon}"


class TaskStatus(ExtendedEnum[TaskStatusEnum], enum_type=TaskStatusEnum):
    DRAFT = TaskStatusEnum(0, "Draft", "Draft", "✍🏼")
    IN_PROGRESS = TaskStatusEnum(1, "In Progress", "Task is being worked on.", "📌")
    COMPLETED = TaskStatusEnum(2, "Completed", "Task is completed.", "✅")

    FAILED = TaskStatusEnum(11, "Failed", "Task has failed.", "❌")
    ARCHIVED = TaskStatusEnum(12, "Archived", "Task is archived.", "🗃️")
    CANCELLED = TaskStatusEnum(13, "Cancelled", "Task has been cancelled.", "🚫")