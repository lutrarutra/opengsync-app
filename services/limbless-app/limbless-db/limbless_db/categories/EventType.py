from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class EventTypeEnum(DBEnum):
    color: str


class EventType(ExtendedEnum[EventTypeEnum], enum_type=EventTypeEnum):
    CUSTOM = EventTypeEnum(0, "Custom", "#d63384")
    SAMPLE_SUBMISSION = EventTypeEnum(1, "Sample Submission", "#fd7e14")

    @classmethod
    def to_color_legend(cls) -> dict[str, str]:
        return dict([(e.name, e.color) for e in cls.as_list()])
            