from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship


from ..categories import DataPathType
from ..core.EnumColumn import EnumColumn
from .Base import Base

if TYPE_CHECKING:
    from .Project import Project
    from .Experiment import Experiment
    from .Library import Library
    from .SeqRequest import SeqRequest


class DataPath(Base):
    __tablename__ = "data_path"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(sa.String(2048), nullable=False, unique=False, index=True)
    type: Mapped[DataPathType] = mapped_column(EnumColumn[DataPathType](DataPathType), nullable=False, name="type_id", key="type")

    library_id: Mapped[int | None] = mapped_column(sa.ForeignKey("library.id"), nullable=True)
    library: Mapped["Library | None"] = relationship("Library", back_populates="data_paths", lazy="select")

    project_id: Mapped[int | None] = mapped_column(sa.ForeignKey("project.id"), nullable=True)
    project: Mapped["Project | None"] = relationship("Project", back_populates="data_paths", lazy="select")

    experiment_id: Mapped[int | None] = mapped_column(sa.ForeignKey("experiment.id"), nullable=True)
    experiment: Mapped["Experiment | None"] = relationship("Experiment", back_populates="data_paths", lazy="select")

    seq_request_id: Mapped[int | None] = mapped_column(sa.ForeignKey("seq_request.id"), nullable=True)
    seq_request: Mapped["SeqRequest | None"] = relationship("SeqRequest", back_populates="data_paths", lazy="select")

    def __str__(self):
        return f"DataPath(id={self.id}, path='{self.path}', type={self.type.name})"
    
    def __repr__(self):
        return self.__str__()