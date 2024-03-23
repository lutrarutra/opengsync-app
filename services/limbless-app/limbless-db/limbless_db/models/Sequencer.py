from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base

from ..categories import SequencerType, SequencerTypeEnum


class Sequencer(Base):
    __tablename__ = "sequencer"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)

    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, unique=True, index=True)
    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, unique=False)

    @property
    def type(self) -> SequencerTypeEnum:
        return SequencerType.get(self.type_id)