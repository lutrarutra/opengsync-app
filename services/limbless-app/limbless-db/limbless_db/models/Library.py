from typing import Optional, TYPE_CHECKING, ClassVar
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Links import LibraryFeatureLink

from .Base import Base
from .SeqRequest import SeqRequest
from ..categories import LibraryType, LibraryTypeEnum, LibraryStatus, LibraryStatusEnum, GenomeRef, GenomeRefEnum

if TYPE_CHECKING:
    from .Pool import Pool
    from .Links import SampleLibraryLink
    from .CMO import CMO
    from .User import User
    from .IndexKit import IndexKit
    from .Feature import Feature
    from .VisiumAnnotation import VisiumAnnotation
    from .SeqQuality import SeqQuality


@dataclass
class Index:
    sequence: Optional[str]
    adapter: Optional[str]


class Library(Base):
    __tablename__ = "library"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    genome_ref_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None)

    volume: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    dna_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    total_size: Mapped[Optional[int]] = mapped_column(sa.Float, nullable=True, default=None)
    seq_depth_requested: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)

    num_samples: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    num_features: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    index_kit_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("indexkit.id"), nullable=True)
    index_kit: Mapped[Optional["IndexKit"]] = relationship("IndexKit", lazy="select")

    pool_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("pool.id"), nullable=True)
    pool: Mapped[Optional["Pool"]] = relationship("Pool", back_populates="libraries", lazy="joined")

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="libraries", lazy="joined")

    sample_links: Mapped[list["SampleLibraryLink"]] = relationship(
        "SampleLibraryLink", back_populates="library", lazy="select", cascade="save-update, merge, delete, delete-orphan",
    )

    features: Mapped[list["Feature"]] = relationship("Feature", secondary=LibraryFeatureLink.__tablename__, lazy="select")

    seq_request_id: Mapped[int] = mapped_column(sa.ForeignKey("seqrequest.id"), nullable=False)
    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", back_populates="libraries", lazy="select")

    adapter: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    index_1_sequence: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    index_2_sequence: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    index_3_sequence: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    index_4_sequence: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    read_qualities: Mapped[list["SeqQuality"]] = relationship("SeqQuality", back_populates="library", lazy="select", cascade="delete")

    visium_annotation_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("visiumannotation.id"), nullable=True, default=None)
    visium_annotation: Mapped[Optional["VisiumAnnotation"]] = relationship("VisiumAnnotation", lazy="select", cascade="delete")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "type_id", "status_id", "owner_id", "pool_id", "adapter"]

    def to_dict(self):
        res = {
            "library_id": self.id,
            "library_name": self.name,
            "library_type": self.type.abbreviation,
            "pool": self.pool.name if self.pool is not None else None,
            "adapter": self.adapter,
            "index_1": self.index_1_sequence,
            "index_2": self.index_2_sequence,
            "index_3": self.index_3_sequence,
            "index_4": self.index_4_sequence,
        }

        return res
    
    @property
    def status(self) -> LibraryStatusEnum:
        return LibraryStatus.get(self.status_id)

    @property
    def type(self) -> LibraryTypeEnum:
        return LibraryType.get(self.type_id)
    
    @property
    def genome_ref(self) -> Optional[GenomeRefEnum]:
        if self.genome_ref_id is None:
            return None
        return GenomeRef.get(self.genome_ref_id)
    
    def is_multiplexed(self) -> bool:
        return self.num_samples > 1
    
    def is_editable(self) -> bool:
        return self.status == LibraryStatus.DRAFT
    
    # TODO: Remove
    @property
    def indices(self) -> list[Optional[Index]]:
        return [
            Index(self.index_1_sequence, self.adapter) if self.index_1_sequence is not None else None,
            Index(self.index_2_sequence, self.adapter) if self.index_2_sequence is not None else None,
            Index(self.index_3_sequence, self.adapter) if self.index_3_sequence is not None else None,
            Index(self.index_4_sequence, self.adapter) if self.index_4_sequence is not None else None,
        ]

    def is_indexed(self) -> bool:
        return self.index_1_sequence is not None
    
    def is_pooled(self) -> bool:
        return self.pool_id is not None
    
    def __str__(self) -> str:
        return f"Library(id: {self.id}, name: {self.name}, type: {self.type})"