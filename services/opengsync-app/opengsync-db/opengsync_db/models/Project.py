from typing import TYPE_CHECKING, ClassVar
from datetime import datetime
from datetime import timezone

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict


from .Base import Base
from .. import localize
from ..categories import ProjectStatus, ProjectStatusEnum

if TYPE_CHECKING:
    from .Sample import Sample
    from .User import User
    from .Group import Group
    from .Library import Library
    from .DataPath import DataPath
<<<<<<< HEAD
    from .ShareToken import ShareToken
=======
>>>>>>> 3bf9919ded1998d0ff25beefa9bcbc3530e447a5


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    identifier: Mapped[str | None] = mapped_column(sa.String(16), default=None, nullable=True, index=True)
    title: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(sa.String(1024), default=None, nullable=True)

    timestamp_created_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    data_paths: Mapped[list["DataPath"]] = relationship("DataPath", back_populates="project", lazy="select")
    samples: Mapped[list["Sample"]] = relationship("Sample", back_populates="project", lazy="select")
    libraries: Mapped[list["Library"]] = relationship(
        "Library",
        secondary="join(SampleLibraryLink, Sample, SampleLibraryLink.sample_id == Sample.id)",
        primaryjoin="Project.id == Sample.project_id",
        secondaryjoin="SampleLibraryLink.library_id == Library.id",
        order_by="Library.id",
        viewonly=True,
        lazy="select",
    )

    share_token_uuid: Mapped[str | None] = mapped_column(sa.ForeignKey("share_token.uuid", ondelete="SET NULL"), nullable=True)
    share_token: Mapped["ShareToken | None"] = relationship("ShareToken", lazy="select")

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="projects", lazy="joined")

    group_id: Mapped[int | None] = mapped_column(sa.ForeignKey("group.id"), nullable=True)
    group: Mapped["Group | None"] = relationship("Group", back_populates="projects", lazy="joined", foreign_keys=[group_id], cascade="save-update, merge")

    __software: Mapped[dict[str, dict] | None] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None, name="software")

    sortable_fields: ClassVar[list[str]] = ["id", "identifier", "title", "owner_id", "status_id", "group_id", "timestamp_created_utc", "num_samples"]

    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        if "samples" in orm.attributes.instance_state(self).unloaded:
            return len(self.samples)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_samples' attribute.")
        from .Sample import Sample
        return session.query(sa.func.count(Sample.id)).filter(Sample.project_id == self.id).scalar()
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .Sample import Sample
        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            Sample.project_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_data_paths(self) -> int:  # type: ignore[override]
        if "data_paths" in orm.attributes.instance_state(self).unloaded:
            return len(self.data_paths)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_data_paths' attribute.")
        from .DataPath import DataPath
        return session.query(sa.func.count(DataPath.id)).filter(DataPath.project_id == self.id).scalar()

    @num_data_paths.expression
    def num_data_paths(cls) -> sa.ScalarSelect[int]:
        from .DataPath import DataPath
        return sa.select(
            sa.func.count(DataPath.id)
        ).where(
            DataPath.project_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @property
    def software(self) -> dict[str, dict]:
        return self.__software or {}

    def set_software(self, software: str, version: str, comment: str | None = None) -> None:
        if self.__software is None:
            self.__software = {}
        software = software.strip().lower()
        self.__software[software] = {
            "version": version,
            "timestamp": datetime.now().isoformat()
        }
        if comment is not None:
            self.__software[software]["comment"] = comment
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        if self.identifier is not None:
            return self.identifier + (f" ({self.title})" if self.title else "")
        return self.title
    
    @property
    def status(self) -> ProjectStatusEnum:
        return ProjectStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: ProjectStatusEnum):
        self.status_id = value.id

    @property
    def timestamp_created(self) -> datetime:
        return localize(self.timestamp_created_utc)

    def timestamp_created_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp_created.strftime(fmt)
    
    def __str__(self) -> str:
        if self.identifier:
            return f"Project(id: {self.id}, identifier: {self.identifier})"
        return f"Project(id: {self.id}, title: {self.title})"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    __table_args__ = (
        sa.Index(
            "trgm_project_identifier_idx",
            sa.text("lower(identifier) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        sa.Index(
            "trgm_project_title_idx",
            sa.text("lower(title) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )