from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class RunStatusEnum(DBEnum):
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon


class RunStatus(ExtendedEnum[RunStatusEnum], enum_type=RunStatusEnum):
    IDLE = RunStatusEnum(0, "Idle", "⌛")
    RUNNING = RunStatusEnum(1, "Running", "🟢")
    FINISHED = RunStatusEnum(2, "Finished", "✅")
    ARCHIVED = RunStatusEnum(10, "Archived", "🗃️")
    FAILED = RunStatusEnum(11, "Failed", "❌")