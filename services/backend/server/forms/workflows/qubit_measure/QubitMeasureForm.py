import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C, SyncSession, queries as Q

from ....core import dependencies, responses
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn, CategoricalDropDown
from ...HTMXForm import RouteFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .QubitMeasureWorkflow import QubitMeasureWorkflow, QubitMeasureWorkflowStep

class SubForm(SubHTMXForm):
    id_ = inputs.numeric.IntInputField("ID", required=True, read_only=True)
    qubit_concentration = inputs.numeric.FloatInputField("Qubit Concentration (ng/µL)", required=False, ge=0.0)

class QubitMeasureForm(QubitMeasureWorkflowStep):
    template_path = "workflows/qubit-measure/complete.html"

    sample_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    library_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    pool_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    lane_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)

    def prepare(self):
        from ....core.context import ctx
        
        sample_ids = self.workflow.metadata.get("selected_sample_ids", [])
        library_ids = self.workflow.metadata.get("selected_library_ids", [])
        pool_ids = self.workflow.metadata.get("selected_pool_ids", [])
        lane_ids = self.workflow.metadata.get("selected_lane_ids", [])

        for sample_id in sample_ids:
            sample = ctx.session.get_one(Q.sample.select(id=sample_id))
            entry = self.sample_forms.append_entry()
            entry.id_.data = sample.id
            entry.qubit_concentration.data = sample.qubit_concentration

        for library_id in library_ids:
            library = ctx.session.get_one(Q.library.select(id=library_id))
            entry = self.library_forms.append_entry()
            entry.id_.data = library.id
            entry.qubit_concentration.data = library.qubit_concentration
        
        for pool_id in pool_ids:
            pool = ctx.session.get_one(Q.pool.select(id=pool_id))
            entry = self.pool_forms.append_entry()
            entry.id_.data = pool.id
            entry.qubit_concentration.data = pool.qubit_concentration

        for lane_id in lane_ids:
            lane = ctx.session.get_one(Q.lane.select(id=lane_id))
            entry = self.lane_forms.append_entry()
            entry.id_.data = lane.id
            entry.qubit_concentration.data = lane.original_qubit_concentration

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "QubitMeasureForm" = Depends(QubitMeasureForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            for entry in form.sample_forms.entries:
                sample = session.get_one(Q.sample.select(id=entry.id_.data))
                sample.qubit_concentration = entry.qubit_concentration.data

            for entry in form.library_forms.entries:
                library = session.get_one(Q.library.select(id=entry.id_.data))
                library.qubit_concentration = entry.qubit_concentration.data

            for entry in form.pool_forms.entries:
                pool = session.get_one(Q.pool.select(id=entry.id_.data))
                pool.qubit_concentration = entry.qubit_concentration.data
                if pool.status == C.PoolStatus.ACCEPTED:
                    pool.status = C.PoolStatus.STORED

            for entry in form.lane_forms.entries:
                lane = session.get_one(Q.lane.select(id=entry.id_.data))
                lane.original_qubit_concentration = entry.qubit_concentration.data

            next_url = responses.url_for("dashboard")
            if form.workflow.experiment_id:
                next_url = responses.url_for("experiment_page", experiment_id=form.workflow.experiment_id)
            elif form.workflow.lab_prep_id:
                next_url = responses.url_for("lab_prep_page", lab_prep_id=form.workflow.lab_prep_id)

            form.workflow.complete()
            return responses.htmx_response(
                redirect=next_url,
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route

