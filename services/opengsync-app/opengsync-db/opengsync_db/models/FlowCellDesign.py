from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from . import links
from ..categories import ExperimentWorkFlow, ExperimentWorkFlowEnum
from .Experiment import Experiment

if TYPE_CHECKING:
    from .PoolDesign import PoolDesign


class FlowCellDesign(Base):
    __tablename__ = "flow_cell_design"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(Experiment.name.type.length), nullable=False, index=True)

    workflow_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    cycles_r1: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    cycles_r2: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    pool_design_links: Mapped[list["links.DesignPoolFlowCellLink"]] = relationship(
        "links.DesignPoolFlowCellLink", back_populates="flow_cell_design", lazy="select",
        cascade="all, delete-orphan",
    )

    @property
    def workflow(self) -> ExperimentWorkFlowEnum:
        return ExperimentWorkFlow.get(self.workflow_id)
    
    @workflow.setter
    def workflow(self, value: ExperimentWorkFlowEnum):
        self.workflow_id = value.id

    __table_args__ = (
        sa.Index(
            "trgm_fc_design_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )