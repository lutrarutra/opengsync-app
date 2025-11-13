from datetime import datetime
from datetime import timezone
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from ..categories import ExperimentStatus, ExperimentStatusEnum, FlowCellTypeEnum, ExperimentWorkFlow, ExperimentWorkFlowEnum, LibraryType, LibraryTypeEnum, MediaFileType
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
    operator: Mapped["User"] = relationship("User", lazy="select")

    sequencer_id: Mapped[int] = mapped_column(sa.ForeignKey("sequencer.id"), nullable=False)
    sequencer: Mapped["Sequencer"] = relationship("Sequencer", lazy="select")

    seq_run: Mapped[Optional["SeqRun"]] = relationship("SeqRun", lazy="joined", primaryjoin="Experiment.name == SeqRun.experiment_name", foreign_keys=name, post_update=True)
    lane_pooling_table: Mapped[Optional["MediaFile"]] = relationship(
        "MediaFile", lazy="select", viewonly=True, uselist=False,
        primaryjoin=f"and_(Experiment.id == MediaFile.experiment_id, MediaFile.type_id ==  {MediaFileType.LANE_POOLING_TABLE.id})",
    )

    pools: Mapped[list["Pool"]] = relationship("Pool", lazy="select", back_populates="experiment")
    libraries: Mapped[list["Library"]] = relationship("Library", lazy="select", back_populates="experiment")
    lanes: Mapped[list["Lane"]] = relationship("Lane", lazy="select", order_by="Lane.number", cascade="merge, save-update, delete, delete-orphan")
    media_files: Mapped[list["MediaFile"]] = relationship("MediaFile", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")
    read_qualities: Mapped[list["SeqQuality"]] = relationship("SeqQuality", back_populates="experiment", lazy="select", cascade="delete")
    laned_pool_links: Mapped[list[links.LanePoolLink]] = relationship("LanePoolLink", lazy="select", cascade="delete, delete-orphan")
    data_paths: Mapped[list["DataPath"]] = relationship("DataPath", back_populates="experiment", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "flowcell_id", "timestamp_created_utc", "timestamp_finished_utc", "status_id", "sequencer_id", "flowcell_type_id", "workflow_id"]

    def get_checklist(self) -> dict:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open for checklist")
        
        pools_added = len(self.pools) > 0
        lanes_assigned = self.workflow.combined_lanes or all(len(pool.lane_links) > 0 for pool in self.pools) if pools_added else None
        reads_assigned = True if pools_added else None
        missing_pool_reads = set()

        for lane in self.lanes:
            if len(lane.pool_links) == 1:
                continue
            
            for pool_link in lane.pool_links:
                if pool_link.num_m_reads is None:
                    reads_assigned = False if pools_added else None
                    missing_pool_reads.add(pool_link.pool.name)

        pool_qubits_measured = all(pool.qubit_concentration is not None for pool in self.pools) if pools_added else None
        pool_fragment_sizes_measured = all(pool.avg_fragment_size is not None for pool in self.pools) if pools_added else None
        laning_completed = all(len(lane.pool_links) == 1 for lane in self.lanes) if pools_added else None

        if not laning_completed:
            if self.lane_pooling_table is not None:
                laning_completed = True if pools_added else None
                
        for pool in self.pools:
            if len(pool.lane_links) < 1:
                laning_completed = False if pools_added else None
                break
                
        lane_qubit_measured = True
        lane_fragment_size_measured = True
        missing_lane_qubits = set()
        missing_lane_fragment_sizes = set()

        for lane in self.lanes:
            _lane_qubit_measured = lane.original_qubit_concentration is not None or ((len(lane.pool_links) == 1) and (lane.pool_links[0].pool.qubit_concentration is not None))
            _lane_fragment_size_measured = lane.avg_fragment_size is not None or ((len(lane.pool_links) == 1) and (lane.pool_links[0].pool.avg_fragment_size is not None))

            lane_qubit_measured = lane_qubit_measured and _lane_qubit_measured
            lane_fragment_size_measured = lane_fragment_size_measured and _lane_fragment_size_measured
            if not _lane_qubit_measured:
                missing_lane_qubits.add(f"Lane {lane.number}")
            if not _lane_fragment_size_measured:
                missing_lane_fragment_sizes.add(f"Lane {lane.number}")

        # if the lane fragment sizes are not measured, check that we have the prerequisites
        if not lane_fragment_size_measured:
            if not laning_completed:
                lane_fragment_size_measured = None

        if not lane_qubit_measured:
            if not laning_completed:
                lane_qubit_measured = None

        flowcell_loaded = all(lane.is_loaded() for lane in self.lanes)
        # if not all lanes are loaded, check that we have the prerequisites
        if not flowcell_loaded:
             if not lane_qubit_measured or not lane_fragment_size_measured:
                 flowcell_loaded = None

        return {
            "pools_added": pools_added,
            "lanes_assigned": lanes_assigned,
            "reads_assigned": reads_assigned,
            "missing_pool_reads": missing_pool_reads,
            "pool_qubits_measured": pool_qubits_measured,
            "pool_fragment_sizes_measured": pool_fragment_sizes_measured,
            "lane_qubit_measured": lane_qubit_measured,
            "missing_lane_qubits": missing_lane_qubits,
            "lane_fragment_size_measured": lane_fragment_size_measured,
            "missing_lane_fragment_sizes": missing_lane_fragment_sizes,
            "laning_completed": laning_completed,
            "flowcell_loaded": flowcell_loaded,
        }
    
    def get_loaded_reads(self) -> float:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open for checklist")
        reads = 0.0
        for lane in self.lanes:
            for link in lane.pool_links:
                if link.num_m_reads is not None:
                    reads += link.num_m_reads
        return reads

    @hybrid_property
    def library_types(self) -> list[LibraryTypeEnum]:
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            types = {library.type_id for library in self.libraries}
            return [LibraryType.get(type_id) for type_id in sorted(types)]
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'library_types' attribute.")
        from .Library import Library
        type_ids = session.query(Library.type_id).filter(Library.experiment_id == self.id).distinct().order_by(Library.type_id).all()
        return [LibraryType.get(type_id) for (type_id,) in type_ids]

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
    
    @property
    def read_config(self) -> str:
        return f"{self.r1_cycles}-{self.i1_cycles}-{self.i2_cycles or 0}-{self.r2_cycles or 0}"
    
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