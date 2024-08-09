from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class EventTypeEnum(DBEnum):
    color: str


class EventType(ExtendedEnum[EventTypeEnum], enum_type=EventTypeEnum):
    CUSTOM = EventTypeEnum(0, "Custom", "#F3F3F3")
    SAMPLE_SUBMISSION = EventTypeEnum(1, "Sample Submission", "#FFD700")