from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base
from ..categories import SequencerModel, SequencerModel
from ..core.EnumColumn import EnumColumn


class Sequencer(Base):
    __tablename__ = "sequencer"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)

    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, unique=True, index=True)
    model: Mapped[SequencerModel] = mapped_column(EnumColumn[SequencerModel](SequencerModel), nullable=False, name="model_id", key="model")
    ip: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, unique=False)

    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> str | None:
        return self.model.name
    
    def search_value(self) -> int:
        return self.id
    
    def __str__(self) -> str:
        return f"Sequencer('{self.name}', '{self.model.name}')"
    
    def __repr__(self) -> str:
        return self.__str__()