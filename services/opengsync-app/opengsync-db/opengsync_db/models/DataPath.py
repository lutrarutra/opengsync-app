from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship


from ..categories import DataPathType, DataPathTypeEnum
from .Base import Base

if TYPE_CHECKING:
    from .Project import Project
    from .Experiment import Experiment
    from .Library import Library


class DataPath(Base):
    __tablename__ = "data_path"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(sa.String(2048), nullable=False, unique=False, index=True)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    library_id: Mapped[int | None] = mapped_column(sa.ForeignKey("library.id"), nullable=True)
    library: Mapped["Library | None"] = relationship("Library", back_populates="data_paths", lazy="select")

    project_id: Mapped[int | None] = mapped_column(sa.ForeignKey("project.id"), nullable=True)
    project: Mapped["Project | None"] = relationship("Project", back_populates="data_paths", lazy="select")

    experiment_id: Mapped[int | None] = mapped_column(sa.ForeignKey("experiment.id"), nullable=True)
    experiment: Mapped["Experiment | None"] = relationship("Experiment", back_populates="data_paths", lazy="select")

    seq_request_id: Mapped[int | None] = mapped_column(sa.ForeignKey("seq_request.id"), nullable=True)
    seq_request = relationship("SeqRequest", back_populates="data_paths", lazy="select")

    @property
    def type(self) -> DataPathTypeEnum:
        return DataPathType.get(self.type_id)
    
    @type.setter
    def type(self, value: DataPathTypeEnum) -> None:
        self.type_id = value.id

    def __str__(self):
        return f"DataPath(id={self.id}, path='{self.path}', type={self.type.name})"
    
    def __repr__(self):
        return self.__str__()