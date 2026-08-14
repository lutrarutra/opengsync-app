from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class EventTypeEnum(DBEnum):
    label: str
    color: str


class EventType(ExtendedEnum):
    label: str
    color: str

    CUSTOM = EventTypeEnum(0, label="Custom", color="#d63384")
    SAMPLE_SUBMISSION = EventTypeEnum(1, label="Sample Submission", color="#fd7e14")

    @classmethod
    def to_color_legend(cls) -> dict[str, str]:
        return {e.label: e.color for e in cls.as_list()}
 