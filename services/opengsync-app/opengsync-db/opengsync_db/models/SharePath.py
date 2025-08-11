import uuid as uuid_lib
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .ShareToken import ShareToken


class SharePath(Base):
    __tablename__ = "share_path"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(sa.ForeignKey("share_token.uuid"), nullable=False)
    path: Mapped[str] = mapped_column(sa.String(512), nullable=False)

    token: Mapped["ShareToken"] = relationship("ShareToken", back_populates="paths", lazy="select")

    __table_args__ = (sa.UniqueConstraint("uuid", "path", name="uq_uuid_path"), )
