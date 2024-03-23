import os

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from ..categories import FileType, FileTypeEnum
from .User import User


class File(Base):
    __tablename__ = "file"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    extension: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    uuid: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    
    uploader_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    uploader: Mapped["User"] = relationship("User", back_populates="files", lazy="select")

    @property
    def type(self) -> FileTypeEnum:
        return FileType.get(self.type_id)
    
    @property
    def path(self) -> str:
        return os.path.join(self.type.dir, f"{self.uuid}{self.extension}")