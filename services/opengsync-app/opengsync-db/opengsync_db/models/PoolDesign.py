from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from .Pool import Pool


if TYPE_CHECKING:
    from .FlowCellDesign import FlowCellDesign
    from .TODOComment import TODOComment

class PoolDesign(Base):
    __tablename__ = "pool_design"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(Pool.name.type.length), nullable=False, index=True)

    cycles_r1: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    cycles_i1: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    cycles_i2: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    cycles_r2: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    pool_id: Mapped[int | None] = mapped_column(sa.ForeignKey("pool.id", ondelete="SET NULL"), nullable=True)
    pool: Mapped["Pool | None"] = relationship("Pool", lazy="select")

    flow_cell_design_id: Mapped[int | None] = mapped_column(sa.ForeignKey("flow_cell_design.id", ondelete="SET NULL"), nullable=True)
    flow_cell_design: Mapped["FlowCellDesign | None"] = relationship("FlowCellDesign", lazy="select")

    num_m_requested_reads: Mapped[float | None] = mapped_column(sa.Float, nullable=True, default=None)
    comments: Mapped[list["TODOComment"]] = relationship("TODOComment", lazy="select", cascade="all, delete-orphan", order_by="TODOComment.timestamp_utc.desc()")

    __table_args__ = (
        sa.Index(
            "trgm_pool_design_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )