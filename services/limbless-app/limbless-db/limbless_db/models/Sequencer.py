from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base

from ..categories import SequencerModel, SequencerModelEnum


class Sequencer(Base):
    __tablename__ = "sequencer"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)

    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, unique=True, index=True)
    model_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, unique=False)

    @property
    def model(self) -> SequencerModelEnum:
        return SequencerModel.get(self.model_id)
    
    @model.setter
    def model(self, value: SequencerModelEnum):
        self.model_id = value.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> str | None:
        return self.model.name
    
    def search_value(self) -> int:
        return self.id