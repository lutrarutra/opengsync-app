from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class RunStatusEnum(DBEnum):
    label: str
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon


class RunStatus(ExtendedEnum):
    label: str
    icon: str
    IDLE = RunStatusEnum(0, "Idle", "⌛")
    RUNNING = RunStatusEnum(1, "Running", "🟢")
    FINISHED = RunStatusEnum(2, "Finished", "✅")
    ARCHIVED = RunStatusEnum(10, "Archived", "🗃️")
    FAILED = RunStatusEnum(11, "Failed", "❌")