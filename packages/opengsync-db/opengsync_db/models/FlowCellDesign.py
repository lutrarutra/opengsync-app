from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from ..categories import ExperimentWorkFlow, ExperimentWorkFlow, FlowCellType, FlowCellType, TaskStatus, TaskStatus

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

    _num_m_reads: Mapped[float | None] = orm.query_expression()

    @hybrid_property
    def num_m_reads(self) -> float:  # type: ignore[override]
        if self._num_m_reads is not None:
            return self._num_m_reads

        if "pool_design_links" in orm.attributes.instance_state(self).unloaded:
            total = 0.0
            for pd in self.pool_designs:
                if pd.num_m_requested_reads is not None:
                    total += pd.num_m_requested_reads
            return total
        
        if self._is_async_context():
            raise RuntimeError(
                "num_m_reads was not populated via with_expression. "
                "Use orm.with_expression(FlowCellDesign._num_m_reads, FlowCellDesign.num_m_reads.expression) "
                "in your query options."
            )

        from .PoolDesign import PoolDesign
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")

        return session.query(sa.func.coalesce(sa.func.sum(PoolDesign.num_m_requested_reads), 0.0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()

    @num_m_reads.expression
    def num_m_reads(cls) -> sa.ScalarSelect[float]:
        from .PoolDesign import PoolDesign
        return sa.select(
            sa.func.coalesce(sa.func.sum(PoolDesign.num_m_requested_reads), 0.0)
        ).where(
            PoolDesign.flow_cell_design_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    _r1_cycles: Mapped[int | None] = orm.query_expression()
    _i1_cycles: Mapped[int | None] = orm.query_expression()
    _i2_cycles: Mapped[int | None] = orm.query_expression()
    _r2_cycles: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def r1_cycles(self) -> int:  # type: ignore[override]
        if self._r1_cycles is not None:
            return self._r1_cycles

        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_r1 for pd in self.pool_designs), default=0)

        if self._is_async_context():
            raise RuntimeError(
                "r1_cycles was not populated via with_expression. "
                "Use orm.with_expression(FlowCellDesign._r1_cycles, FlowCellDesign.r1_cycles.expression) "
                "in your query options."
            )

        from .PoolDesign import PoolDesign
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")

        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_r1), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()

    @r1_cycles.expression
    def r1_cycles(cls) -> sa.ScalarSelect[int]:
        from .PoolDesign import PoolDesign
        return sa.select(
            sa.func.coalesce(sa.func.max(PoolDesign.cycles_r1), 0)
        ).where(
            PoolDesign.flow_cell_design_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def i1_cycles(self) -> int:  # type: ignore[override]
        if self._i1_cycles is not None:
            return self._i1_cycles

        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_i1 for pd in self.pool_designs), default=0)

        if self._is_async_context():
            raise RuntimeError(
                "i1_cycles was not populated via with_expression. "
                "Use orm.with_expression(FlowCellDesign._i1_cycles, FlowCellDesign.i1_cycles.expression) "
                "in your query options."
            )

        from .PoolDesign import PoolDesign
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")

        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_i1), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()

    @i1_cycles.expression
    def i1_cycles(cls) -> sa.ScalarSelect[int]:
        from .PoolDesign import PoolDesign
        return sa.select(
            sa.func.coalesce(sa.func.max(PoolDesign.cycles_i1), 0)
        ).where(
            PoolDesign.flow_cell_design_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def i2_cycles(self) -> int:  # type: ignore[override]
        if self._i2_cycles is not None:
            return self._i2_cycles

        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_i2 for pd in self.pool_designs), default=0)

        if self._is_async_context():
            raise RuntimeError(
                "i2_cycles was not populated via with_expression. "
                "Use orm.with_expression(FlowCellDesign._i2_cycles, FlowCellDesign.i2_cycles.expression) "
                "in your query options."
            )

        from .PoolDesign import PoolDesign
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")

        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_i2), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()

    @i2_cycles.expression
    def i2_cycles(cls) -> sa.ScalarSelect[int]:
        from .PoolDesign import PoolDesign
        return sa.select(
            sa.func.coalesce(sa.func.max(PoolDesign.cycles_i2), 0)
        ).where(
            PoolDesign.flow_cell_design_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def r2_cycles(self) -> int:  # type: ignore[override]
        if self._r2_cycles is not None:
            return self._r2_cycles

        if "pool_designs" in orm.attributes.instance_state(self).unloaded:
            return max((pd.cycles_r2 for pd in self.pool_designs), default=0)

        if self._is_async_context():
            raise RuntimeError(
                "r2_cycles was not populated via with_expression. "
                "Use orm.with_expression(FlowCellDesign._r2_cycles, FlowCellDesign.r2_cycles.expression) "
                "in your query options."
            )

        from .PoolDesign import PoolDesign
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("FlowCellDesign instance is not bound to a session.")

        return session.query(sa.func.coalesce(sa.func.max(PoolDesign.cycles_r2), 0)).filter(
            PoolDesign.flow_cell_design_id == self.id
        ).scalar()

    @r2_cycles.expression
    def r2_cycles(cls) -> sa.ScalarSelect[int]:
        from .PoolDesign import PoolDesign
        return sa.select(
            sa.func.coalesce(sa.func.max(PoolDesign.cycles_r2), 0)
        ).where(
            PoolDesign.flow_cell_design_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]            
    
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
    def workflow(self) -> ExperimentWorkFlow:
        return ExperimentWorkFlow.get(self.workflow_id)
    
    @property
    def num_lanes(self) -> int:
        return self.workflow.flow_cell_type.num_lanes
    
    @workflow.setter
    def workflow(self, value: ExperimentWorkFlow):
        self.workflow_id = value.id

    @property
    def task_status(self) -> TaskStatus:
        return TaskStatus.get(self.task_status_id)
    
    @task_status.setter
    def task_status(self, status: TaskStatus) -> None:
        self.task_status_id = status.id

    __table_args__ = (
        sa.Index(
            "trgm_fc_design_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    @property
    def flow_cell_type(self) -> FlowCellType | None:
        if self.flow_cell_type_id is None:
            num_m_reads = self.num_m_reads
            diff = float('inf')

            flow_cell_types = FlowCellType.as_list()
            selected_type = flow_cell_types[0]

            for fc_type in flow_cell_types:
                current_diff = fc_type.max_m_reads - num_m_reads
                fit = current_diff > 0 or abs(current_diff) / fc_type.max_m_reads < 0.1
                if fit and current_diff < diff:
                    diff = current_diff
                    selected_type = fc_type

            return selected_type
        return FlowCellType.get(self.flow_cell_type_id)
    
    @flow_cell_type.setter
    def flow_cell_type(self, fc_type: FlowCellType | None) -> None:
        if fc_type is None:
            self.flow_cell_type_id = None
        else:
            self.flow_cell_type_id = fc_type.id