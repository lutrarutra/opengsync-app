from typing import Self

from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc
from ....core.context import ctx
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .LaneQCWorkflow import LaneQCWorkflow, LaneQCWorkflowStep
from .UnifiedQCLanesForm import LaneQCRow


class QCLanesSubForm(SubHTMXForm):
    lane_id = inputs.numeric.IntInputField("Lane ID", required=True, hidden=True, read_only=True)
    phi_x = inputs.numeric.FloatInputField("Phi X %", required=True, ge=0.0, unit="%")
    avg_fragment_size = inputs.numeric.IntInputField("Average Library Size", required=True, ge=0, unit="bp")
    qubit_concentration = inputs.numeric.FloatInputField("Qubit Concentration", required=True, ge=0.0, unit="ng/μL")


class QCLanesForm(LaneQCWorkflowStep):
    workflow: LaneQCWorkflow
    template_path = "workflows/experiment/lane_qc-1.1.html"

    fields = inputs.dynamic.SubFormList[QCLanesSubForm](min_elements=1)

    def __init__(self, workflow: LaneQCWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.experiment: models.Experiment | None = None

    def _set_context(self, experiment: models.Experiment, session: SyncSession) -> None:
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["df"] = session.pd.get_experiment_lanes(experiment.id)
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity

    def get_context(self) -> dict:
        context = super().get_context()
        df = context.get("df")
        if df is not None:
            context["lanes"] = list(zip(df.to_dict("records"), list(self.fields)))
        return context

    @classmethod
    def build(cls, workflow: LaneQCWorkflow, session: SyncSession) -> Self:
        experiment = session.get_one(
            Q.experiment.select(id=workflow.experiment_id),
            options=[orm.selectinload(models.Experiment.lanes)],
        )
        form = cls(workflow=workflow)
        form._set_context(experiment, session)

        if ctx.request.method == "GET":
            for _, row in parsing.safe_iter(form._context["df"], LaneQCRow):
                entry = form.fields.append_entry()
                entry.lane_id.data = row.id
                if row.phi_x is not None:
                    entry.phi_x.data = row.phi_x
                qubit = (
                    row.sequencing_qubit_concentration
                    if row.sequencing_qubit_concentration is not None
                    else row.original_qubit_concentration
                )
                if qubit is not None:
                    entry.qubit_concentration.data = qubit
                if row.avg_fragment_size is not None:
                    entry.avg_fragment_size.data = int(row.avg_fragment_size)
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LaneQCWorkflow = Depends(LaneQCWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> QCLanesForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: QCLanesForm = Depends(QCLanesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            for entry in form.fields:
                lane = session.first(Q.lane.select(id=entry.lane_id.data))
                if lane is None:
                    raise exc.ItemNotFoundException(f"Lane with id {entry.lane_id.data} not found.")
                lane.original_qubit_concentration = entry.qubit_concentration.data
                lane.avg_fragment_size = entry.avg_fragment_size.data
                lane.phi_x = entry.phi_x.data
                session.save(lane)
            return form.workflow.complete_to_experiment()
        return route
