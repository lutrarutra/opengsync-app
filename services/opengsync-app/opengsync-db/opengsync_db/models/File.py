import os
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from uuid_extensions import uuid7str

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base
from ..categories import FileType, FileTypeEnum
from .User import User

if TYPE_CHECKING:
    from .Comment import Comment


class File(Base):
    __tablename__ = "file"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    extension: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    uuid: Mapped[str] = mapped_column(sa.CHAR(36), nullable=False, default=lambda: uuid7str(), unique=True)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    uploader_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    uploader: Mapped["User"] = relationship("User", back_populates="files", lazy="joined")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="file", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")

    seq_request_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("seq_request.id"), nullable=True)
    experiment_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("experiment.id"), nullable=True)
    lab_prep_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("lab_prep.id"), nullable=True)

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