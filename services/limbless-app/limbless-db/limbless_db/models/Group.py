import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from .Links import UserAffiliation
from ..categories import GroupType, GroupTypeEnum


class Group(Base):
    __tablename__ = "group"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True, unique=True)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    user_links: Mapped[list[UserAffiliation]] = relationship("UserAffiliation", back_populates="group", lazy="select", cascade="all, save-update, merge")

    @property
    def type(self) -> GroupTypeEnum:
        return GroupType.get(self.type_id)
    
    @type.setter
    def type(self, value: GroupTypeEnum):
        self.type_id = value.id
    
    def __str__(self) -> str:
        return f"Group(id: {self.id}, name: {self.name}, type: {self.type})"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name