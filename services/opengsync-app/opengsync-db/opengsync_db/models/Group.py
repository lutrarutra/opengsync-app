import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from . import links
from ..categories import GroupType, GroupTypeEnum, AffiliationType

from typing import TYPE_CHECKING, ClassVar
if TYPE_CHECKING:
    from .Project import Project
    from .SeqRequest import SeqRequest
    from .User import User


class Group(Base):
    __tablename__ = "group"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True, unique=True)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    user_links: Mapped[list[links.UserAffiliation]] = relationship("UserAffiliation", back_populates="group", lazy="select", cascade="all, save-update, merge")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="group", lazy="select")
    seq_requests: Mapped[list["SeqRequest"]] = relationship("SeqRequest", back_populates="group", lazy="select")

    owner: Mapped["User"] = relationship(
        "User",
        secondary="join(links.UserAffiliation, User, links.UserAffiliation.user_id == User.id)",
        primaryjoin=f"and_(Group.id == links.UserAffiliation.group_id, links.UserAffiliation.affiliation_type_id == {AffiliationType.OWNER.id})",
        secondaryjoin="User.id == links.UserAffiliation.user_id",
        uselist=False,
        viewonly=True,
        lazy="select",
    )

    sortable_fields: ClassVar[list[str]] = ["id", "type_id", "num_users", "num_seq_requests", "num_projects"]

    @hybrid_property
    def num_projects(self) -> int:  # type: ignore[override]
        if "projects" not in orm.attributes.instance_state(self).unloaded:
            return len(self.projects)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_projects' attribute.")
        
        from .Project import Project
        return session.query(sa.func.count(Project.id)).filter(Project.group_id == self.id).scalar()
    
    @num_projects.expression
    def num_projects(cls) -> sa.ScalarSelect[int]:
        from .Project import Project
        return sa.select(
            sa.func.count(Project.id)
        ).where(
            Project.group_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_seq_requests(self) -> int:  # type: ignore[override]
        if "seq_requests" not in orm.attributes.instance_state(self).unloaded:
            return len(self.seq_requests)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_seq_requests' attribute.")
        
        from .SeqRequest import SeqRequest
        return session.query(sa.func.count(SeqRequest.id)).filter(SeqRequest.group_id == self.id).scalar()
    
    @num_seq_requests.expression
    def num_seq_requests(cls) -> sa.ScalarSelect[int]:
        from .SeqRequest import SeqRequest
        return sa.select(
            sa.func.count(SeqRequest.id)
        ).where(
            SeqRequest.group_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_users(self) -> int:  # type: ignore[override]
        if "user_links" not in orm.attributes.instance_state(self).unloaded:
            return len(self.user_links)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_users' attribute.")
        
        return session.query(sa.func.count(links.UserAffiliation.user_id)).filter(links.UserAffiliation.group_id == self.id).scalar()
    
    @num_users.expression
    def num_users(cls) -> sa.ScalarSelect[int]:
        return sa.select(
            sa.func.count(links.UserAffiliation.user_id)
        ).where(
            links.UserAffiliation.group_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

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

    __table_args__ = (
        sa.Index(
            "trgm_group_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )