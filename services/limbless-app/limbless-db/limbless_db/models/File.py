import os
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
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
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=False), nullable=False, default=sa.func.now())
    
    uploader_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    uploader: Mapped["User"] = relationship("User", back_populates="files", lazy="joined")

    @property
    def type(self) -> FileTypeEnum:
        return FileType.get(self.type_id)
    
    @property
    def path(self) -> str:
        return os.path.join(self.type.dir, f"{self.uuid}{self.extension}")

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)
    
    def size_str(self) -> str:
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 ** 2:
            return f"{self.size_bytes / 1024:.1f} KB"
        elif self.size_bytes < 1024 ** 3:
            return f"{self.size_bytes / 1024 ** 2:.1f} MB"
        else:
            return f"{self.size_bytes / 1024 ** 3:.1f} GB"
        
    def timestamp_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")