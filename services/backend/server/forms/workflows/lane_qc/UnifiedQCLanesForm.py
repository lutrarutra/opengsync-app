from typing import Self

from fastapi import Depends, Response
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies
from ....core.context import ctx
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LaneQCWorkflow import LaneQCWorkflow, LaneQCWorkflowStep


class LaneQCRow(BaseModel):
    id: int
    lane: int
    phi_x: float | None = None
    original_qubit_concentration: float | None = None
    sequencing_qubit_concentration: float | None = None
    avg_fragment_size: float | int | None = None


class UnifiedQCLanesForm(LaneQCWorkflowStep):
    workflow: LaneQCWorkflow
    template_path = "workflows/experiment/lane_qc-1.2.html"

    phi_x = inputs.numeric.FloatInputField("Phi X %", required=True, ge=0.0, unit="%")
    avg_fragment_size = inputs.numeric.IntInputField("Average Library Size", required=True, ge=0, unit="bp")
    qubit_concentration = inputs.numeric.FloatInputField("Qubit Concentration", required=True, ge=0.0, unit="ng/μL")

    def __init__(self, workflow: LaneQCWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.experiment: models.Experiment | None = None

    def _set_context(self, experiment: models.Experiment) -> None:
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity

    @classmethod
    def build(cls, workflow: LaneQCWorkflow, session: SyncSession) -> Self:
        experiment = session.get_one(
            Q.experiment.select(id=workflow.experiment_id),
            options=[orm.selectinload(models.Experiment.lanes)],
        )
        form = cls(workflow=workflow)
        form._set_context(experiment)

        df = session.pd.get_experiment_lanes(experiment.id)
        rows = list(parsing.safe_iter(df, LaneQCRow))
        if rows:
            _, row = rows[0]
            qubit = (
                row.sequencing_qubit_concentration
                if row.sequencing_qubit_concentration is not None
                else row.original_qubit_concentration
            )
            if ctx.request.method == "GET":
                form.phi_x.data = row.phi_x
                form.avg_fragment_size.data = int(row.avg_fragment_size) if row.avg_fragment_size is not None else None
                form.qubit_concentration.data = qubit
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LaneQCWorkflow = Depends(LaneQCWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> UnifiedQCLanesForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: UnifiedQCLanesForm = Depends(UnifiedQCLanesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            assert form.experiment is not None
            for lane in form.experiment.lanes:
                lane.phi_x = form.phi_x.data
                lane.avg_fragment_size = form.avg_fragment_size.data
                lane.original_qubit_concentration = form.qubit_concentration.data
                session.save(lane)
            return form.workflow.complete_to_experiment()
        return route
