from datetime import datetime
from datetime import timezone
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from ..categories import ExperimentStatus, ExperimentStatusEnum, FlowCellTypeEnum, ExperimentWorkFlow, ExperimentWorkFlowEnum
from .Base import Base
from . import links

if TYPE_CHECKING:
    from .Pool import Pool
    from .Sequencer import Sequencer
    from .User import User
    from .MediaFile import MediaFile
    from .Comment import Comment
    from .SeqQuality import SeqQuality
    from .SeqRun import SeqRun
    from .Lane import Lane
    from .Library import Library
    from .DataPath import DataPath


class Experiment(Base):
    __tablename__ = "experiment"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(16), nullable=False, unique=True, index=True)
    
    timestamp_created_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    timestamp_finished_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)
    
    r1_cycles: Mapped[int] = mapped_column(nullable=False)
    r2_cycles: Mapped[Optional[int]] = mapped_column(nullable=True)
    i1_cycles: Mapped[int] = mapped_column(nullable=False)
    i2_cycles: Mapped[Optional[int]] = mapped_column(nullable=True)

    workflow_id: Mapped[int] = mapped_column(sa.SmallInteger)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)

    operator_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    operator: Mapped["User"] = relationship("User", lazy="joined")

    sequencer_id: Mapped[int] = mapped_column(sa.ForeignKey("sequencer.id"), nullable=False)
    sequencer: Mapped["Sequencer"] = relationship("Sequencer", lazy="select")

    seq_run: Mapped[Optional["SeqRun"]] = relationship("SeqRun", lazy="joined", primaryjoin="Experiment.name == SeqRun.experiment_name", foreign_keys=name, post_update=True)

    pools: Mapped[list["Pool"]] = relationship("Pool", lazy="select", back_populates="experiment")
    libraries: Mapped[list["Library"]] = relationship("Library", lazy="select", back_populates="experiment")
    lanes: Mapped[list["Lane"]] = relationship("Lane", lazy="select", order_by="Lane.number", cascade="merge, save-update, delete, delete-orphan")
    media_files: Mapped[list["MediaFile"]] = relationship("MediaFile", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")
    read_qualities: Mapped[list["SeqQuality"]] = relationship("SeqQuality", back_populates="experiment", lazy="select", cascade="delete")
    laned_pool_links: Mapped[list[links.LanePoolLink]] = relationship("LanePoolLink", lazy="select", cascade="delete, delete-orphan")
    data_paths: Mapped[list["DataPath"]] = relationship("DataPath", back_populates="experiment", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "flowcell_id", "timestamp_created_utc", "timestamp_finished_utc", "status_id", "sequencer_id", "flowcell_type_id", "workflow_id"]

    @hybrid_property
    def num_pools(self) -> int:  # type: ignore[override]
        if "pools" not in orm.attributes.instance_state(self).unloaded:
            return len(self.pools)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_pools' attribute.")
        from .Pool import Pool
        return session.query(sa.func.count(Pool.id)).filter(Pool.experiment_id == self.id).scalar()  # type: ignore[arg-type]
    
    @num_pools.expression
    def num_pools(cls) -> sa.ScalarSelect[int]:
        from .Pool import Pool
        return sa.select(
            sa.func.count(Pool.id)
        ).where(
            Pool.experiment_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_libraries(self) -> int:  # type: ignore[override]
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return len(self.libraries)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_libraries' attribute.")
        from .Library import Library
        return session.query(sa.func.count(Library.id)).filter(Library.experiment_id == self.id).scalar()
    
    @num_libraries.expression
    def num_libraries(cls) -> sa.ScalarSelect[int]:
        from .Library import Library
        return sa.select(
            sa.func.count(Library.id)
        ).where(
            Library.experiment_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_files(self) -> int:  # type: ignore[override]
        if "files" not in orm.attributes.instance_state(self).unloaded:
            return len(self.media_files)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_files' attribute.")
        from .MediaFile import MediaFile
        return session.query(sa.func.count(MediaFile.id)).filter(MediaFile.experiment_id == self.id).count()
    
    @num_files.expression
    def num_files(cls) -> sa.ScalarSelect[int]:
        from .MediaFile import MediaFile
        return sa.select(
            sa.func.count(sa.distinct(MediaFile.id))
        ).where(
            MediaFile.experiment_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_comments(self) -> int:  # type: ignore[override]
        if "comments" not in orm.attributes.instance_state(self).unloaded:
            return len(self.comments)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_comments' attribute.")
        from .Comment import Comment
        return session.query(sa.func.count(Comment.id)).filter(Comment.experiment_id == self.id).scalar()
    
    @num_comments.expression
    def num_comments(cls) -> sa.ScalarSelect[int]:
        from .Comment import Comment
        return sa.select(
            sa.func.count(Comment.id)
        ).where(
            Comment.experiment_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @property
    def num_dilutions(self) -> int:
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_dilutions' attribute.")
        
        from .Pool import Pool
        from .PoolDilution import PoolDilution
        return session.query(sa.func.count(PoolDilution.id)).where(
            sa.exists().where(
                sa.and_(
                    PoolDilution.pool_id == Pool.id,
                    Pool.experiment_id == self.id
                )
            )
        ).scalar()
    
    @hybrid_property
    def num_projects(self) -> int:  # type: ignore[override]
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_projects' attribute.")
        
        from .Project import Project
        from .Sample import Sample
        from .Library import Library

        return session.query(sa.func.count(Project.id)).where(
            sa.exists().where(
                sa.and_(
                    Sample.project_id == Project.id,
                    links.SampleLibraryLink.sample_id == Sample.id,
                    Library.id == links.SampleLibraryLink.library_id,
                    Library.experiment_id == self.id,
                )
            )
        ).scalar()
    
    @num_projects.expression
    def num_projects(cls) -> sa.ScalarSelect[int]:
        from .Project import Project
        from .Sample import Sample
        from .Library import Library

        return sa.select(
            sa.func.count(Project.id)
        ).where(
            sa.exists().where(
                sa.and_(
                    Sample.project_id == Project.id,
                    links.SampleLibraryLink.sample_id == Sample.id,
                    Library.id == links.SampleLibraryLink.library_id,
                    Library.experiment_id == cls.id,
                )
            )
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_data_paths(self) -> int:  # type: ignore[override]
        if "data_paths" not in orm.attributes.instance_state(self).unloaded:
            return len(self.data_paths)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_data_paths' attribute.")
        from .DataPath import DataPath
        return session.query(sa.func.count(DataPath.id)).filter(DataPath.experiment_id == self.id).scalar()
    
    @num_data_paths.expression
    def num_data_paths(cls) -> sa.ScalarSelect[int]:
        from .DataPath import DataPath
        return sa.select(
            sa.func.count(DataPath.id)
        ).where(
            DataPath.experiment_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @property
    def status(self) -> ExperimentStatusEnum:
        return ExperimentStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: ExperimentStatusEnum):
        self.status_id = value.id
    
    @property
    def flowcell_type(self) -> FlowCellTypeEnum:
        return self.workflow.flow_cell_type
    
    @flowcell_type.setter
    def flowcell_type(self, value: FlowCellTypeEnum):
        self.workflow_id = value.id
    
    @property
    def workflow(self) -> ExperimentWorkFlowEnum:
        return ExperimentWorkFlow.get(self.workflow_id)
    
    @workflow.setter
    def workflow(self, value: ExperimentWorkFlowEnum):
        self.workflow_id = value.id
    
    @property
    def timestamp_created(self) -> datetime:
        return localize(self.timestamp_created_utc)
    
    @property
    def timestamp_finished(self) -> datetime | None:
        if self.timestamp_finished_utc is None:
            return None
        return localize(self.timestamp_finished_utc)
    
    def is_deleteable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_editable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def is_submittable(self) -> bool:
        return self.status == ExperimentStatus.DRAFT
    
    def timestamp_created_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp_created.strftime(fmt)
    
    def timestamp_finished_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        if (ts := self.timestamp_finished) is None:
            return ""
        return ts.strftime(fmt)
    
    @property
    def num_lanes(self) -> int:
        return self.flowcell_type.num_lanes
    
    def __str__(self) -> str:
        return f"Experiment(id={self.id}, name={self.name}, flowcell={self.flowcell_type.name}, workflow={self.workflow.name}, status={self.status.name})"
    
    def __repr__(self) -> str:
        return str(self)
    
    def search_name(self) -> str:
        return self.name
    
    def search_value(self) -> int:
        return self.id
    
    def m_reads_planned(self) -> float:
        reads = 0.0
        for lane in self.lanes:
            reads += lane.m_reads_planned()
        return reads
    
    __table_args__ = (
        sa.Index(
            "trgm_experiment_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )