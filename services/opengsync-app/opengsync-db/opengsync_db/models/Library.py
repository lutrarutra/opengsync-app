from typing import Optional, TYPE_CHECKING, ClassVar
from datetime import datetime
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict

from . import links
from .Base import Base
from .SeqRequest import SeqRequest
from ..categories import (
    LibraryType, LibraryTypeEnum, LibraryStatus, LibraryStatusEnum, GenomeRef,
    GenomeRefEnum, ServiceType, ServiceTypeEnum, MUXType, MUXTypeEnum, IndexType, IndexTypeEnum
)

if TYPE_CHECKING:
    from .Pool import Pool
    from .User import User
    from .Feature import Feature
    from .SeqQuality import SeqQuality
    from .MediaFile import MediaFile
    from .LibraryIndex import LibraryIndex
    from .LabPrep import LabPrep
    from .Experiment import Experiment
    from .DataPath import DataPath
    from .Protocol import Protocol


@dataclass
class LibraryAdapter:
    name_i7: str
    _name_i5: str | None
    sequences_i7: list[str]
    sequences_i5: list[str | None]

    @property
    def name_i5(self) -> str:
        return self._name_i5 if self._name_i5 is not None else self.name_i7


class Library(Base):
    __tablename__ = "library"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(86), nullable=False)
    sample_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    clone_number: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)

    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    genome_ref_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    service_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    mux_type_id: Mapped[Optional[int]] = mapped_column(sa.SmallInteger, nullable=True, default=None)
    index_type_id: Mapped[Optional[int]] = mapped_column(sa.SmallInteger, nullable=True, default=None)

    timestamp_stored_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)

    nuclei_isolation: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    seq_depth_requested: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    avg_fragment_size: Mapped[Optional[int]] = mapped_column(sa.Float, nullable=True, default=None)
    volume: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    properties: Mapped[Optional[dict]] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None)

    ba_report_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("media_file.id"), nullable=True, default=None)
    ba_report: Mapped[Optional["MediaFile"]] = relationship("MediaFile", lazy="select")

    pool_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("pool.id", ondelete="SET NULL"), nullable=True)
    pool: Mapped[Optional["Pool"]] = relationship(
        "Pool", back_populates="libraries", lazy="select", cascade="save-update, merge"
    )

    experiment_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("experiment.id"), nullable=True, default=None)
    experiment: Mapped[Optional["Experiment"]] = relationship("Experiment", lazy="select", back_populates="libraries")

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="libraries", lazy="select")
    
    seq_request_id: Mapped[int] = mapped_column(sa.ForeignKey("seq_request.id"), nullable=False)
    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", back_populates="libraries", lazy="select")
    
    lab_prep_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("lab_prep.id"), nullable=True)
    lab_prep: Mapped[Optional["LabPrep"]] = relationship("LabPrep", back_populates="libraries", lazy="select")

    protocol_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("protocol.id", ondelete="SET NULL"), nullable=True)
    protocol: Mapped[Optional["Protocol"]] = relationship("Protocol", lazy="select")

    original_library_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("library.id", ondelete="SET NULL"), nullable=True, default=None)
    original_library: Mapped[Optional["Library"]] = relationship("Library", remote_side=[id], lazy="select")

    sample_links: Mapped[list[links.SampleLibraryLink]] = relationship(
        links.SampleLibraryLink, back_populates="library", lazy="select",
        cascade="all, delete-orphan", order_by=links.SampleLibraryLink.sample_id
    )
    features: Mapped[list["Feature"]] = relationship("Feature", secondary=links.LibraryFeatureLink.__tablename__, lazy="select", cascade="save-update, merge")
    plate_links: Mapped[list["links.SamplePlateLink"]] = relationship("SamplePlateLink", back_populates="library", lazy="select", cascade="all, delete, delete-orphan")
    indices: Mapped[list["LibraryIndex"]] = relationship("LibraryIndex", lazy="select", cascade="all, save-update, merge, delete, delete-orphan")
    read_qualities: Mapped[list["SeqQuality"]] = relationship("SeqQuality", back_populates="library", lazy="select", cascade="all, save-update, merge, delete, delete-orphan", order_by="SeqQuality.lane")
    data_paths: Mapped[list["DataPath"]] = relationship("DataPath", back_populates="library", lazy="select", cascade="all, delete, delete-orphan")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "type_id", "status_id", "service_type_id", "owner_id", "pool_id", "adapter", "num_samples", "num_features"]

    def get_num_sequenced_reads(self) -> int:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open")
        total_reads = 0
        for rq in self.read_qualities:
            total_reads += rq.num_reads
        return total_reads

    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        if "sample_links" not in orm.attributes.instance_state(self).unloaded:
            return len(self.sample_links)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_samples' attribute.")
        
        from .Sample import Sample
        return session.query(sa.func.count(Sample.id)).where(
            sa.exists().where(
                sa.and_(
                    Sample.id == links.SampleLibraryLink.sample_id,
                    links.SampleLibraryLink.library_id == self.id
                )
            )
        ).scalar()
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .Sample import Sample
        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            sa.exists().where(
                sa.and_(
                    Sample.id == links.SampleLibraryLink.sample_id,
                    links.SampleLibraryLink.library_id == cls.id
                )
            )
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_features(self) -> int:  # type: ignore[override]
        if "features" not in orm.attributes.instance_state(self).unloaded:
            return len(self.features)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot access 'num_features' attribute.")
        from .Feature import Feature
        return session.query(sa.func.count(Feature.id)).where(
            sa.exists().where(
                sa.and_(
                    Feature.id == links.LibraryFeatureLink.feature_id,
                    links.LibraryFeatureLink.library_id == self.id
                )
            )
        ).scalar()

    @num_features.expression
    def num_features(cls) -> sa.ScalarSelect[int]:
        from .Feature import Feature
        return sa.select(
            sa.func.count(Feature.id)
        ).where(
            sa.exists().where(
                sa.and_(
                    Feature.id == links.LibraryFeatureLink.feature_id,
                    links.LibraryFeatureLink.library_id == cls.id
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
        return session.query(sa.func.count(DataPath.id)).filter(DataPath.library_id == self.id).scalar()
    
    @num_data_paths.expression
    def num_data_paths(cls) -> sa.ScalarSelect[int]:
        from .DataPath import DataPath
        return sa.select(
            sa.func.count(DataPath.id)
        ).where(
            DataPath.library_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @property
    def status(self) -> LibraryStatusEnum:
        return LibraryStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: LibraryStatusEnum):
        self.status_id = value.id

    @property
    def type(self) -> LibraryTypeEnum:
        return LibraryType.get(self.type_id)
    
    @type.setter
    def type(self, value: LibraryTypeEnum):
        self.type_id = value.id
    
    @property
    def genome_ref(self) -> GenomeRefEnum:
        return GenomeRef.get(self.genome_ref_id)
    
    @genome_ref.setter
    def genome_ref(self, value: GenomeRefEnum):
        self.genome_ref_id = value.id

    @property
    def service_type(self) -> ServiceTypeEnum:
        return ServiceType.get(self.service_type_id)
    
    @service_type.setter
    def service_type(self, value: ServiceTypeEnum):
        self.service_type_id = value.id

    @property
    def mux_type(self) -> MUXTypeEnum | None:
        if self.mux_type_id is None:
            return None
        return MUXType.get(self.mux_type_id)
    
    @mux_type.setter
    def mux_type(self, value: MUXTypeEnum | None):
        if value is None:
            self.mux_type_id = None
        else:
            self.mux_type_id = value.id

    @property
    def index_type(self) -> IndexTypeEnum | None:
        if self.index_type_id is None:
            return None
        return IndexType.get(self.index_type_id)
    
    @index_type.setter
    def index_type(self, value: IndexTypeEnum | None):
        if value is None:
            self.index_type_id = None
        else:
            self.index_type_id = value.id
    
    @property
    def qubit_concentration_str(self) -> str:
        if (q := self.qubit_concentration) is None:
            return ""
        return f"{q:.2f}"
    
    @property
    def molarity(self) -> float | None:
        if self.avg_fragment_size is None or self.qubit_concentration is None:
            return None
        return self.qubit_concentration / (self.avg_fragment_size * 660) * 1_000_000
    
    @property
    def molarity_str(self) -> str:
        if (m := self.molarity) is None:
            return ""
        return f"{m:.2f}"
    
    @property
    def timestamp_stored_str(self) -> str:
        return self.timestamp_stored_utc.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp_stored_utc is not None else ""
    
    def is_multiplexed(self) -> bool:
        return self.mux_type_id is not None
    
    def is_editable(self) -> bool:
        return self.status == LibraryStatus.DRAFT
    
    def is_indexed(self) -> bool:
        return len(self.indices) > 0
    
    def is_pooled(self) -> bool:
        return self.status == LibraryStatus.POOLED
    
    def __str__(self) -> str:
        return f"Library(id: {self.id}, name: {self.name}, type: {self.type})"
    
    def __repr__(self) -> str:
        return str(self)
    
    def adapters_i7(self) -> dict[tuple[int, str], list[str]]:
        adapters = {}
        for index in self.indices:
            idx = (index.index_kit_i7_id, index.name_i7)
            if idx not in adapters:
                adapters[idx] = []
            adapters[idx].append(index.sequence_i7)
        return adapters
    
    def adapters_i5(self) -> dict[tuple[int, str], list[str]]:
        adapters = {}
        for index in self.indices:
            if index.sequence_i5 is None:
                continue
            idx = (index.index_kit_i5_id, index.name_i5)
            if idx not in adapters:
                adapters[idx] = []
            adapters[idx].append(index.sequence_i5)
        return adapters

    def sequences_i7_str(self, sep: str = ", ") -> str:
        i7s = []
        for index in self.indices:
            if index.sequence_i7:
                i7s.append(index.sequence_i7)

        return sep.join(i7s)
    
    def sequences_i5_str(self, sep: str = ", ") -> str:
        i5s = []
        for index in self.indices:
            if index.sequence_i5:
                i5s.append(index.sequence_i5)

        return sep.join(i5s)
    
    def names_i7_str(self, sep: str = ", ") -> str:
        i7s = []
        for index in self.indices:
            if index.name_i7:
                i7s.append(index.name_i7)

        return sep.join(i7s)
    
    def names_i5_str(self, sep: str = ", ") -> str:
        i5s = []
        for index in self.indices:
            if index.name_i5:
                i5s.append(index.name_i5)

        return sep.join(i5s)
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name

    __table_args__ = (
        sa.Index(
            "trgm_library_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        sa.Index(
            "trgm_library_sample_name_idx",
            sa.text("lower(sample_name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )