import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .Base import Base


class VisiumAnnotation(Base):
    __tablename__ = "visiumannotation"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    slide: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    area: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    image: Mapped[str] = mapped_column(sa.String(128), nullable=False)