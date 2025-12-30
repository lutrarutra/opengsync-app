from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from . import links
from .Pool import Pool


if TYPE_CHECKING:
    from .User import User
    from .FlowCellDesign import FlowCellDesign

class PoolDesign(Base):
    __tablename__ = "pool_design"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(Pool.name.type.length), nullable=False, index=True)

    pool_id: Mapped[int | None] = mapped_column(sa.ForeignKey("pool.id", ondelete="SET NULL"), nullable=True)
    pool: Mapped["Pool | None"] = relationship("Pool", lazy="select")

    flow_cell_design_links: Mapped[list["links.DesignPoolFlowCellLink"]] = relationship(
        "links.DesignPoolFlowCellLink", back_populates="pool_design", lazy="select",
        cascade="all, delete-orphan",
    )

    num_m_requested_reads: Mapped[float | None] = mapped_column(sa.Float, nullable=True, default=None)

    @property
    def lanes(self) -> list[int]:
        return [link.lane_num for link in self.flow_cell_design_links]
    
    @property
    def num_m_planned_reads(self) -> float:
        total_reads = 0.0
        for link in self.flow_cell_design_links:
            if link.num_m_reads:
                total_reads += link.num_m_reads
        return total_reads

    __table_args__ = (
        sa.Index(
            "trgm_pool_design_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )