

from fastapi import Request
from fastapi.responses import Response

from opengsync_db import models, queries as Q, SyncSession

from ...core import exceptions, responses
from ..HTMXForm import HTMXForm
from ...components import inputs


class PoolDesignForm(HTMXForm):
    template_path = "forms/pool_design.html"

    pool_design_name = inputs.string.StringInputField(
        "Name",
        max_length=models.PoolDesign.name.type.length,
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

    def __init__(
        self,
        request: Request,
        pool_design: models.PoolDesign | None = None,
    ):
        super().__init__(request)
        self.pool_design = pool_design
        self._context["pool_design"] = pool_design

    def prepare(self) -> None:
        if not self.pool_design:
            return
        self.pool_design_name.data = self.pool_design.name
        self.r1_cycles.data = self.pool_design.cycles_r1
        self.r2_cycles.data = self.pool_design.cycles_r2
        self.i1_cycles.data = self.pool_design.cycles_i1
        self.i2_cycles.data = self.pool_design.cycles_i2
        self.num_m_requested_reads.data = self.pool_design.num_m_requested_reads
        if self.pool_design.pool:
            self.pool_id.data = self.pool_design.pool_id

    def _save(self) -> None:
        session: SyncSession = self.request.state.db_session

        if self.pool_design is not None:
            pool_id = self.pool_id.data
            if pool_id:
                pool = session.get_one(Q.pool.select(id=pool_id))
                if pool.num_m_reads_requested:
                    self.pool_design.num_m_requested_reads = pool.num_m_reads_requested
                else:
                    pool.num_m_reads_requested = self.pool_design.num_m_requested_reads
                self.pool_design.name = pool.name
                self.pool_design.pool_id = pool_id
            else:
                self.pool_design.name = self.pool_design_name.data

            self.pool_design.num_m_requested_reads = self.num_m_requested_reads.data
            self.pool_design.cycles_r1 = self.r1_cycles.data
            self.pool_design.cycles_i1 = self.i1_cycles.data
            self.pool_design.cycles_r2 = self.r2_cycles.data
            self.pool_design.cycles_i2 = self.i2_cycles.data
        else:
            new_design = Q.pool_design.create(
                name=self.pool_design_name.data,
                num_m_requested_reads=self.num_m_requested_reads.data,
                cycles_r1=self.r1_cycles.data,
                cycles_i1=self.i1_cycles.data,
                cycles_r2=self.r2_cycles.data,
                cycles_i2=self.i2_cycles.data,
            )
            session.add(new_design)

    def process_request(self) -> Response:
        self.validate()
        self._save()
        return responses.htmx_response(
            redirect=responses.url_for("design"),
            flash=responses.flash("Changes Saved!", "success"),
        )