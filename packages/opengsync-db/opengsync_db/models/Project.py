from typing import TYPE_CHECKING
from datetime import datetime
from datetime import timezone

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict


from .Base import Base
from ..categories import ProjectStatus, LibraryType
from . import links

if TYPE_CHECKING:
    from .Sample import Sample
    from .User import User
    from .Group import Group
    from .Library import Library
    from .DataPath import DataPath
    from .ShareToken import ShareToken
    from .SeqRequest import SeqRequest
    from .Experiment import Experiment


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    identifier: Mapped[str | None] = mapped_column(sa.String(16), default=None, nullable=True, index=True, unique=True)
    title: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(sa.Text, default=None, nullable=True)

    timestamp_created_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    data_paths: Mapped[list["DataPath"]] = relationship("DataPath", back_populates="project", lazy="select")
    samples: Mapped[list["Sample"]] = relationship("Sample", back_populates="project", lazy="select")
    assignees: Mapped[list["User"]] = relationship(
        "User",
        secondary="project_assignee_link",
        back_populates="assigned_projects",
        lazy="select",
    )
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
    owner: Mapped["User"] = relationship("User", back_populates="projects", lazy="select")

    group_id: Mapped[int | None] = mapped_column(sa.ForeignKey("group.id"), nullable=True)
    group: Mapped["Group | None"] = relationship("Group", back_populates="projects", lazy="select", foreign_keys=[group_id], cascade="save-update, merge")

    __software: Mapped[dict[str, dict] | None] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None, name="software")

    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        if self._num_samples is not None:
            return self._num_samples
        
        if "samples" not in orm.attributes.instance_state(self).unloaded:
            return len(self.samples)
        
        if self._is_async_context():
            raise RuntimeError(
                "_num_samples was not populated via with_expression. "
                "Use orm.with_expression(Project._num_samples, Project.num_samples.expression) "
                "in your query options."
            )
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_samples' attribute.")

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.sample.select(project_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Sample import Sample
        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            *Q.sample.where_clauses(project_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_samples: Mapped[int | None] = orm.query_expression()
    
    @hybrid_property
    def library_types(self) -> list[LibraryType]:  # type: ignore[override]
        if self._library_types is not None:
            return [LibraryType.get(type_id) for type_id in self._library_types]

        print(self._library_types)

        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            types = set()
            for lib in self.libraries:
                types.add(lib.type_id)
            return [LibraryType.get(type_id) for type_id in sorted(types)]

        if self._is_async_context():
            raise RuntimeError(
                "_library_types was not populated via with_expression. "
                "Use orm.with_expression(Project._library_types, Project.library_types.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'library_types' attribute.")

        from .. import queries as Q
        from .Library import Library
        result = session.scalar(sa.select(sa.func.array_agg(sa.distinct(Library.type_id))).select_from(
            Q.library.select(project_id=self.id).subquery()
        ))
        if result is None:
            return []
        return [LibraryType.get(type_id) for type_id in result]
    
    @library_types.expression
    def library_types(cls):
        from .. import queries as Q
        from .Library import Library
        return sa.select(
            sa.func.coalesce(
                sa.func.array_agg(sa.distinct(Library.type_id)),
                sa.cast(sa.text("'{}'"), sa.ARRAY(sa.Integer))
            )
        ).where(
            *Q.library.where_clauses(project_id=cls.id)
        ).order_by(Library.type_id).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _library_types: Mapped[list[int] | None] = orm.query_expression()

    @hybrid_property
    def num_data_paths(self) -> int:  # type: ignore[override]
        if self._num_data_paths is not None:
            return self._num_data_paths
        
        if "data_paths" in orm.attributes.instance_state(self).unloaded:
            return len(self.data_paths)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_data_paths' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_data_paths was not populated via with_expression. "
                "Use orm.with_expression(Project._num_data_paths, Project.num_data_paths.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.data_path.select(project_id=self.id).subquery()
        ))  # type: ignore[return-value]

    @num_data_paths.expression
    def num_data_paths(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .DataPath import DataPath
        return sa.select(
            sa.func.count(DataPath.id)
        ).where(
            *Q.data_path.where_clauses(project_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_data_paths: Mapped[int | None] = orm.query_expression()

    _num_assignees: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_assignees(self) -> int:  # type: ignore[override]
        if self._num_assignees is not None:
            return self._num_assignees

        if "assignees" not in orm.attributes.instance_state(self).unloaded:
            return len(self.assignees)

        if self._is_async_context():
            raise RuntimeError(
                "_num_assignees was not populated via with_expression. "
                "Use orm.with_expression(Project._num_assignees, Project.num_assignees.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_assignees.")

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.project.select(id=self.id).subquery()
        ))  # type: ignore[return-value]

    @num_assignees.expression
    def num_assignees(cls) -> sa.ScalarSelect[int]:
        from .User import User
        return sa.select(
            sa.func.count(User.id)
        ).where(
            sa.select(1).where(
                (links.ProjectAssigneeLink.user_id == User.id) &
                (links.ProjectAssigneeLink.project_id == cls.id)
            ).correlate_except(links.ProjectAssigneeLink).exists()
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @property
    def software(self) -> dict[str, dict]:
        return self.__software or {}
    
    @property
    def seq_requests(self) -> list["SeqRequest"]:
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_samples' attribute.")
        
        from .. import queries as Q
        from .SeqRequest import SeqRequest
        return session.query(SeqRequest).where(
            *Q.seq_request.where_clauses(project_id=self.id)
        ).all()
    
    @hybrid_property
    def num_seq_requests(self) -> int:  # type: ignore[override]
        if self._num_seq_requests is not None:
            return self._num_seq_requests

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_seq_requests' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_seq_requests was not populated via with_expression. "
                "Use orm.with_expression(Project._num_seq_requests, Project.num_seq_requests.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.seq_request.select(project_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_seq_requests.expression
    def num_seq_requests(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .SeqRequest import SeqRequest
        return sa.select(
            sa.func.count(sa.distinct(SeqRequest.id))
        ).where(
            *Q.seq_request.where_clauses(project_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_seq_requests: Mapped[int | None] = orm.query_expression()
    
    @property
    def experiments(self) -> list["Experiment"]:
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'experiments' attribute.")
        
        from .. import queries as Q
        from .Experiment import Experiment
        return session.query(Experiment).where(
            *Q.experiment.where_clauses(project_id=self.id)
        ).all()
    
    @hybrid_property
    def num_experiments(self) -> int:  # type: ignore[override]
        if self._num_experiments is not None:
            return self._num_experiments

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_experiments' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_experiments was not populated via with_expression. "
                "Use orm.with_expression(Project._num_experiments, Project.num_experiments.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.experiment.select(project_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_experiments.expression
    def num_experiments(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Experiment import Experiment
        return sa.select(
            sa.func.count(sa.distinct(Experiment.id))
        ).where(
            *Q.experiment.where_clauses(project_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_experiments: Mapped[int | None] = orm.query_expression()
    

    @property
    def share_email_links(self) -> list["links.SeqRequestDeliveryEmailLink"]:
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'share_email_links' attribute.")
        
        from .. import queries as Q
        from .links import SeqRequestDeliveryEmailLink
        from .SeqRequest import SeqRequest
        return session.query(SeqRequestDeliveryEmailLink).where(
            sa.select(1).where(
                *Q.seq_request.where_clauses(project_id=self.id),
                SeqRequestDeliveryEmailLink.seq_request_id == SeqRequest.id
            ).correlate_except(SeqRequest).exists()
        ).all()

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
    def status(self) -> ProjectStatus:
        return ProjectStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: ProjectStatus):
        self.status_id = value.id

    @property
    def timestamp_created(self) -> datetime:
        from .. import localize
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
        sa.UniqueConstraint("title", "owner_id", name="uq_project_title_owner_id")
    )