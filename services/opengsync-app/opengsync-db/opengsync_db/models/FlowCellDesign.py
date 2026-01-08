from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from ..categories import ExperimentWorkFlow, ExperimentWorkFlowEnum, FlowCellType, FlowCellTypeEnum, TaskStatus, TaskStatusEnum

if TYPE_CHECKING:
    from .PoolDesign import PoolDesign
    from .TODOComment import TODOComment


class FlowCellDesign(Base):
    __tablename__ = "flow_cell_design"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)

    task_status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    flow_cell_type_id: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True, default=None)

    pool_designs: Mapped[list["PoolDesign"]] = relationship("PoolDesign", lazy="select", back_populates="flow_cell_design")
    comments: Mapped[list["TODOComment"]] = relationship("TODOComment", lazy="select", cascade="all, delete-orphan", order_by="TODOComment.timestamp_utc.desc()")

    @property
    def num_m_reads(self) -> float:
        if "pool_design_links" in orm.attributes.instance_state(self).unloaded:
            total = 0.0
            for pd in self.pool_designs:
                if pd.num_m_requested_reads is not None:
                    total += pd.num_m_requested_reads
            return total
        
        from .PoolDesign import PoolDesign  # Avoid circular import
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
        
        return session.query(sa.func.coalesce(sa.func.sum(PoolDesign.num_m_requested_reads), 0.0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()
    
    @property
    def r1_cycles(self) -> int:
        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_r1 for pd in self.pool_designs), default=0)
            
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
        
        from .PoolDesign import PoolDesign  # Avoid circular import
        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_r1), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()
    
    @property
    def i1_cycles(self) -> int:
        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_i1 for pd in self.pool_designs), default=0)
            
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
        
        from .PoolDesign import PoolDesign  # Avoid circular import
        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_i1), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()
    
    @property
    def i2_cycles(self) -> int:
        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_i2 for pd in self.pool_designs), default=0)
            
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
        
        from .PoolDesign import PoolDesign  # Avoid circular import
        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_i2), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()
    
    @property
    def r2_cycles(self) -> int:
        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_r2 for pd in self.pool_designs), default=0)
            
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
        
        from .PoolDesign import PoolDesign  # Avoid circular import
        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_r2), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()            
    
    def flow_cell_cycles_requirements(self) -> str:
        if "pool_designs" not in orm.attributes.instance_state(self).unloaded:
            if orm.object_session(self) is None:
                raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")
            
        r1 = 0
        r2 = 0
        i1 = 0
        i2 = 0

        for pool_design in self.pool_designs:
            r1 = max(r1, pool_design.cycles_r1)
            r2 = max(r2, pool_design.cycles_r2)
            i1 = max(i1, pool_design.cycles_i1)
            i2 = max(i2, pool_design.cycles_i2)

        return f"{r1}-{i1}-{i2}-{r2}"

    @property
    def workflow(self) -> ExperimentWorkFlowEnum:
        return ExperimentWorkFlow.get(self.workflow_id)
    
    @property
    def num_lanes(self) -> int:
        return self.workflow.flow_cell_type.num_lanes
    
    @workflow.setter
    def workflow(self, value: ExperimentWorkFlowEnum):
        self.workflow_id = value.id

    @property
    def task_status(self) -> TaskStatusEnum:
        return TaskStatus.get(self.task_status_id)
    
    @task_status.setter
    def task_status(self, status: TaskStatusEnum) -> None:
        self.task_status_id = status.id

    __table_args__ = (
        sa.Index(
            "trgm_fc_design_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    @property
    def flow_cell_type(self) -> FlowCellTypeEnum | None:
        if self.flow_cell_type_id is None:
            num_m_reads = self.num_m_reads
            diff = float('inf')

            flow_cell_types = FlowCellType.as_list()
            selected_type = flow_cell_types[0]

            for fc_type in flow_cell_types:
                current_diff = abs(fc_type.max_m_reads - num_m_reads)
                if current_diff < diff:
                    diff = current_diff
                    selected_type = fc_type

            return selected_type
        return FlowCellType.get(self.flow_cell_type_id)
    
    @flow_cell_type.setter
    def flow_cell_type(self, fc_type: FlowCellTypeEnum | None) -> None:
        if fc_type is None:
            self.flow_cell_type_id = None
        else:
            self.flow_cell_type_id = fc_type.id