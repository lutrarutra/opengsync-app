"""Manual checks and unchecks of checklist steps: who changed which step, and when.

Separate from the status history (`OperationRun` / `StatusChange`): checklist steps are not status
columns, but follows its conventions (actor kept as NULL when the user is deleted, database clock).
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from ..categories import ChecklistType
from ..core.EnumColumn import EnumColumn
from .Base import Base

if TYPE_CHECKING:
    from .User import User


class ChecklistLog(Base):
    __tablename__ = "checklist_log"
    __table_args__ = (
        sa.Index("ix_checklist_log_seq_request_step", "seq_request_id", "step"),
        sa.Index("ix_checklist_log_experiment_step", "experiment_id", "step"),
    )

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    checklist_type: Mapped[ChecklistType] = mapped_column(EnumColumn[ChecklistType](ChecklistType), nullable=False, name="checklist_type_id", key="checklist_type")
    step: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    checked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    """True: the step was checked; False: it was unchecked."""
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()"))

    actor_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("lims_user.id", ondelete="SET NULL"), nullable=True)
    actor: Mapped[Optional["User"]] = relationship("User", lazy="select")

    seq_request_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("seq_request.id", ondelete="CASCADE"), nullable=True)
    experiment_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("experiment.id", ondelete="CASCADE"), nullable=True)

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)

    def timestamp_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp.strftime(fmt)

    def __str__(self) -> str:
        return f"ChecklistLog(id: {self.id}, {self.checklist_type.name}.{self.step}: {'checked' if self.checked else 'unchecked'})"
