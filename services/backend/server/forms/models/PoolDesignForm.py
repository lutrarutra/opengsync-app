from fastapi import Depends, Response

from opengsync_db import SyncSession, models, queries as Q

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import FormFunc, HTMXForm, RouteFunc, htmx_route


class PoolDesignForm(HTMXForm):
    """Create or edit a pool design."""

    template_path = "forms/pool_design.html"

    pool_design_name = inputs.string.StringInputField(
        "Name",
        max_length=models.PoolDesign.name.type.length,
        min_length=1,
        description="Name of the pool design.",
    )
    r1_cycles = inputs.numeric.IntInputField("R1 Cycles", required=True)
    i1_cycles = inputs.numeric.IntInputField("I1 Cycles", required=True)
    i2_cycles = inputs.numeric.IntInputField("I2 Cycles", required=True)
    r2_cycles = inputs.numeric.IntInputField("R2 Cycles", required=True)
    num_m_requested_reads = inputs.numeric.FloatInputField(
        "Number of Requested Reads (Millions)",
        required=True,
        description="Number of requested reads in millions for the pool design.",
    )
    pool_id = inputs.searchable.SearchableInputField(
        "Pool",
        route="search_pools",
        required=False,
    )

    def __init__(self, pool_design: models.PoolDesign | None = None) -> None:
        super().__init__()
        self.pool_design = pool_design

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            pool_design_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "PoolDesignForm":
            pool_design = None
            if pool_design_id is not None:
                pool_design = session.get_one(Q.pool_design.select(id=pool_design_id))
            return cls(pool_design=pool_design)

        return dependency

    def populate_from_design(self) -> None:
        if self.pool_design is None:
            return
        self.pool_design_name.data = self.pool_design.name
        self.r1_cycles.data = self.pool_design.cycles_r1
        self.r2_cycles.data = self.pool_design.cycles_r2
        self.i1_cycles.data = self.pool_design.cycles_i1
        self.i2_cycles.data = self.pool_design.cycles_i2
        self.num_m_requested_reads.data = self.pool_design.num_m_requested_reads or 0.0
        self.pool_id.data = self.pool_design.pool_id

    @htmx_route("GET", "/create-pool-design", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "PoolDesignForm" = Depends(PoolDesignForm.Init()),
            _=Depends(dependencies.require_insider),
        ):
            if form.pool_design is not None:
                raise exc.OpeNGSyncServerException("Pool design must be absent for create form.")
            return form.make_response()
        return route

    @htmx_route("POST", "/create-pool-design", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "PoolDesignForm" = Depends(PoolDesignForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.pool_design is not None:
                raise exc.OpeNGSyncServerException("Pool design must be absent for create form.")
            pool_design = session.save(Q.pool_design.create(
                name=form.pool_design_name.data,
                num_m_requested_reads=form.num_m_requested_reads.data,
                cycles_r1=form.r1_cycles.data,
                cycles_i1=form.i1_cycles.data,
                cycles_i2=form.i2_cycles.data,
                cycles_r2=form.r2_cycles.data,
            ), flush=True)
            if form.pool_id.data:
                pool_design.pool_id = form.pool_id.data
            return responses.htmx_response(
                redirect=responses.url_for("design"),
                flash=responses.flash("Design Created!", "success"),
            )
        return submit

    @htmx_route("GET", "/edit-pool-design", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "PoolDesignForm" = Depends(PoolDesignForm.Init()),
            _=Depends(dependencies.require_insider),
        ):
            if form.pool_design is None:
                raise exc.OpeNGSyncServerException("Pool design ID must be provided for edit form.")
            form.populate_from_design()
            return form.make_response()
        return route

    @htmx_route("POST", "/edit-pool-design", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "PoolDesignForm" = Depends(PoolDesignForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.pool_design is None:
                raise exc.OpeNGSyncServerException("Pool design ID must be provided for edit form.")

            pool_id = form.pool_id.data
            if pool_id:
                pool = session.get_one(Q.pool.select(id=pool_id))
                if pool.num_m_reads_requested:
                    form.pool_design.num_m_requested_reads = pool.num_m_reads_requested
                else:
                    pool.num_m_reads_requested = form.num_m_requested_reads.data
                form.pool_design.name = pool.name
                form.pool_design.pool_id = pool_id
            else:
                form.pool_design.name = form.pool_design_name.data
                form.pool_design.pool_id = None

            form.pool_design.num_m_requested_reads = form.num_m_requested_reads.data
            form.pool_design.cycles_r1 = form.r1_cycles.data
            form.pool_design.cycles_i1 = form.i1_cycles.data
            form.pool_design.cycles_r2 = form.r2_cycles.data
            form.pool_design.cycles_i2 = form.i2_cycles.data
            session.save(form.pool_design, flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("design"),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return submit
