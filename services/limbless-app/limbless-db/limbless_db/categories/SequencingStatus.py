from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SequencingStatusEnum(DBEnum):
    icon: str


class SequencingStatus(ExtendedEnum[SequencingStatusEnum], enum_type=SequencingStatusEnum):
    RUNNING = SequencingStatusEnum(1, "Running", "🧬")
    DONE = SequencingStatusEnum(2, "Done", "✅")
    FAILED = SequencingStatusEnum(3, "Failed", "❌")