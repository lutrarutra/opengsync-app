from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class OperationKindEnum(DBEnum):
    label: str
    implicit: bool
    description: str


class OperationKind(ExtendedEnum):
    label: str
    implicit: bool
    description: str

    ACTION = OperationKindEnum(0, "Action", False, "User action in the web app (form, button)")
    WORKFLOW = OperationKindEnum(1, "Workflow", False, "Multi-step workflow in the web app")
    API = OperationKindEnum(2, "API", False, "REST API call (API token)")
    MANUAL = OperationKindEnum(3, "Manual", False, "Status set by hand in an edit form")
    WORKER = OperationKindEnum(10, "Worker", True, "Automatic change by a celery task")
    MIGRATION = OperationKindEnum(11, "Migration", True, "Database migration")
    SYSTEM = OperationKindEnum(12, "System", True, "Creation defaults and unattributed changes")
