from typing import Optional, TYPE_CHECKING, ClassVar
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from . import links
from ..categories import PoolStatus, PoolStatusEnum, PoolType, PoolTypeEnum
from .Experiment import Experiment

if TYPE_CHECKING:
    from .Library import Library
    from .User import User
    from .SeqRequest import SeqRequest
    from .Lane import Lane
    from .Contact import Contact
    from .MediaFile import MediaFile
    from .PoolDilution import PoolDilution
    from .Plate import Plate
    from .LabPrep import LabPrep


class Pool(Base):
    __tablename__ = "pool"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    timestamp_stored_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)
    clone_number: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    original_pool_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("pool.id", ondelete="SET NULL"), nullable=True, default=None)
    
    num_m_reads_requested: Mapped[Optional[float]] = mapped_column(sa.Float, default=None, nullable=True)
    avg_fragment_size: Mapped[Optional[int]] = mapped_column(sa.Integer, default=None, nullable=True)
    qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, default=None, nullable=True)

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="pools", lazy="joined")

    plate_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("plate.id"), nullable=True)
    plate: Mapped[Optional["Plate"]] = relationship("Plate", lazy="select")

    seq_request_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("seq_request.id"), nullable=True)
    seq_request: Mapped[Optional["SeqRequest"]] = relationship("SeqRequest", lazy="select")
    
    contact_id: Mapped[int] = mapped_column(sa.ForeignKey("contact.id"), nullable=False)
    contact: Mapped["Contact"] = relationship("Contact", lazy="select")

    ba_report_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("media_file.id"), nullable=True, default=None)
    ba_report: Mapped[Optional["MediaFile"]] = relationship("MediaFile", lazy="select", foreign_keys=[ba_report_id])

    lab_prep_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("lab_prep.id"), nullable=True)
    lab_prep: Mapped[Optional["LabPrep"]] = relationship("LabPrep", lazy="select")

    experiment_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("experiment.id"), nullable=True)
    experiment: Mapped[Optional["Experiment"]] = relationship("Experiment", lazy="select", back_populates="pools")

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="pool", lazy="select", order_by="Library.id")
    lane_links: Mapped[list[links.LanePoolLink]] = relationship(
        "LanePoolLink", back_populates="pool", lazy="select",
        cascade="save-update, merge, delete",
        order_by="links.LanePoolLink.lane_num"
    )
    dilutions: Mapped[list["PoolDilution"]] = relationship(
        "PoolDilution", back_populates="pool", lazy="select",
        cascade="merge, save-update, delete, delete-orphan", order_by="PoolDilution.timestamp_utc"
    )

    sortable_fields: ClassVar[list[str]] = ["id", "name", "owner_id", "num_libraries", "num_m_reads_requested", "status_id"]

    warning_min_molarity: ClassVar[float] = 1.0
    warning_max_molarity: ClassVar[float] = 5.0
    error_min_molarity: ClassVar[float] = 0.5
    error_max_molarity: ClassVar[float] = 10.0

    @hybrid_property
    def num_libraries(self) -> int:  # type: ignore[override]
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return len(self.libraries)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_libraries' attribute.")
        from .Library import Library
        return session.query(sa.func.count(Library.id)).filter(Library.pool_id == self.id).scalar()
    
    @num_libraries.expression
    def num_libraries(cls) -> sa.ScalarSelect[int]:
        from .Library import Library
        return sa.select(
            sa.func.count(Library.id)
        ).where(
            Library.pool_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @property
    def status(self) -> PoolStatusEnum:
        return PoolStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: PoolStatusEnum):
        self.status_id = value.id
    
    @property
    def type(self) -> PoolTypeEnum:
        return PoolType.get(self.type_id)
    
    @type.setter
    def type(self, value: PoolTypeEnum):
        self.type_id = value.id
    
    @property
    def molarity(self) -> float | None:
        if self.avg_fragment_size is None or self.qubit_concentration is None:
            return None
        
        return self.qubit_concentration / (self.avg_fragment_size * 660) * 1_000_000
    
    @property
    def molarity_color_class(self) -> str:
        if (molarity := self.molarity) is None:
            return ""
        
        if molarity < self.error_min_molarity or self.error_max_molarity < molarity:
            return "cemm-red"
        
        if molarity < self.warning_min_molarity or self.warning_max_molarity < molarity:
            return "cemm-yellow"
        
        return "cemm-green"
    
    @property
    def qubit_concentration_str(self) -> str:
        if (q := self.qubit_concentration) is None:
            return ""
        return f"{q:.2f}"
    
    @property
    def molarity_str(self) -> str:
        if (m := self.molarity) is None:
            return ""
        return f"{m:.2f}"
    
    @property
    def timestamp_stored_str(self) -> str:
        return self.timestamp_stored_utc.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp_stored_utc is not None else ""
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return f"{self.name}"
    
    def search_description(self) -> str:
        return f"{self.status.name} {self.status.icon}"
    
    def is_qced(self) -> bool:
        return self.qubit_concentration is not None and self.avg_fragment_size is not None
    
    def is_editable(self) -> bool:
        return self.status == PoolStatus.DRAFT
    
    def __str__(self) -> str:
        return f"Pool(id={self.id}, name={self.name})"
    
    def __repr__(self) -> str:
        return str(self)
    
    def lane(self, lane_num: int) -> "tuple[Lane | None, float | None]":
        for link in self.lane_links:
            if link.lane.number == lane_num:
                return link.lane, link.num_m_reads
        return None, None
    
    def reads_planned(self) -> float:
        num_reads = 0.0
        for link in self.lane_links:
            if link.num_m_reads is not None:
                num_reads += link.num_m_reads
        return num_reads
    
    __table_args__ = (
        sa.Index(
            "trgm_pool_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )