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
    def num_m_reads_planned(self) -> float:
        if "pool_design_links" in orm.attributes.instance_state(self).unloaded:
            total = 0.0
            for link in self.pool_design_links:
                if link.pool_design.num_m_requested_reads is not None:
                    total += link.pool_design.num_m_requested_reads
            return total
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
        
        return session.query(sa.func.coalesce(sa.func.sum(links.DesignPoolFlowCellLink.pool_design.has().num_m_requested_reads), 0.0)).filter(
            links.DesignPoolFlowCellLink.flow_cell_design_id == self.id
        ).scalar()

    @property
    def pool_designs(self) -> list["PoolDesign"]:
        if "pool_design_links" in orm.attributes.instance_state(self).unloaded:
            return [link.pool_design for link in self.pool_design_links]
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
        
        from .PoolDesign import PoolDesign
        
        return session.query(PoolDesign).filter(
            sa.exists().where(
                (links.DesignPoolFlowCellLink.flow_cell_design_id == self.id) &
                (links.DesignPoolFlowCellLink.pool_design_id == PoolDesign.id)
            )
        ).all()

    @property
    def workflow(self) -> ExperimentWorkFlowEnum:
        return ExperimentWorkFlow.get(self.workflow_id)
    
    @property
    def num_lanes(self) -> int:
        return self.workflow.flow_cell_type.num_lanes
    
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