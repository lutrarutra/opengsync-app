"""Status history: who changed which status, when, through which operation, and why.

Rows are written by the flush hook in `opengsync_db.transitions.tracking` with Core inserts, so they
never pass through the unit of work. See docs/state-transitions.md.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import DDL, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from ..categories import OperationKind
from ..core.EnumColumn import EnumColumn
from ..transitions import sql as transitions_sql
from .Base import Base

if TYPE_CHECKING:
    from .User import User


class OperationRun(Base):
    """One execution of an operation; groups the status changes it made."""
    __tablename__ = "operation_run"
    __table_args__ = (
        sa.CheckConstraint(transitions_sql.REASON_CHECK, name="ck_operation_run_reason"),
    )

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    operation: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    kind: Mapped[OperationKind] = mapped_column(EnumColumn[OperationKind](OperationKind), nullable=False, name="kind_id", key="kind")

    actor_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("lims_user.id", ondelete="SET NULL"), nullable=True, index=True)
    actor: Mapped[Optional["User"]] = relationship("User", lazy="select")

    subject_type: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    parent_run_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("operation_run.id", ondelete="SET NULL"), nullable=True)
    parent_run: Mapped[Optional["OperationRun"]] = relationship("OperationRun", remote_side=[id], lazy="select")

    comment: Mapped[Optional[str]] = mapped_column(sa.String(512), nullable=True)
    """The user's optional note, e.g. why a status was set by hand."""
    reason: Mapped[Optional[str]] = mapped_column(sa.String(512), nullable=True)
    """System explanation; required for worker, migration and system runs (CHECK constraint)."""
    inferred: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()"))

    changes: Mapped[list["StatusChange"]] = relationship("StatusChange", back_populates="run", lazy="select", order_by="StatusChange.id")

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)

    def __str__(self) -> str:
        return f"OperationRun(id: {self.id}, operation: {self.operation}, kind: {self.kind.name})"


class StatusChange(Base):
    """One status change of one record."""
    __tablename__ = "status_change"
    __table_args__ = (
        sa.Index("ix_status_change_entity_timestamp", "entity_type", "entity_id", "timestamp_utc"),
        sa.Index("ix_status_change_entity_txid", "entity_type", "entity_id", "txid"),
    )

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    run_id: Mapped[int] = mapped_column(sa.ForeignKey("operation_run.id", ondelete="CASCADE"), nullable=False, index=True)
    run: Mapped["OperationRun"] = relationship("OperationRun", back_populates="changes", lazy="joined")

    entity_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    """Table name, e.g. 'library'."""
    entity_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    entity_key: Mapped[Optional[str]] = mapped_column(sa.String(256), nullable=True)
    """Second key for composite primary keys (delivery email)."""
    from_status: Mapped[Optional[int]] = mapped_column(sa.SmallInteger, nullable=True)
    """NULL when the record was created."""
    to_status: Mapped[Optional[int]] = mapped_column(sa.SmallInteger, nullable=True)
    declared: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    """The change matches an effect of the run's operation."""
    inferred: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    detail: Mapped[Optional[str]] = mapped_column(sa.String(512), nullable=True)
    txid: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default=sa.text("txid_current()"))
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()"))

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)

    def __str__(self) -> str:
        return f"StatusChange({self.entity_type} {self.entity_id}: {self.from_status} -> {self.to_status})"


# create_all (tests, fresh installs) installs the commit-time triggers; migrations carry their own copy.
# DDL() %-formats its statement, so the % placeholders of RAISE are escaped.
for _statement in transitions_sql.create_all_statements():
    event.listen(Base.metadata, "after_create", DDL(_statement.replace("%", "%%")).execute_if(dialect="postgresql"))
for _statement in transitions_sql.drop_all_statements():
    event.listen(Base.metadata, "before_drop", DDL(_statement.replace("%", "%%")).execute_if(dialect="postgresql"))
