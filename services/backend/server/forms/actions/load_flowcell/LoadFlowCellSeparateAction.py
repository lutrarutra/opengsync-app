import pandas as pd
from fastapi import Depends
from sqlalchemy import orm
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ....core.context import ctx
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm


class LaneRowSchema(BaseModel):
    total_volume_ul: float | None
    target_molarity: float | None
    lane_molarity: float | None
    sequencing_qubit_concentration: float | None
    phi_x: float | None
    id: int

class LaneSubForm(SubHTMXForm):
    lane_id = inputs.numeric.IntInputField("Lane ID", required=True, read_only=True, hidden=True)
    phi_x = inputs.numeric.FloatInputField("Phi X %", required=True, ge=0.0, unit="%")
    measured_qubit = inputs.numeric.FloatInputField("Qubit Concentration After Dilution", required=False, ge=0.0, unit="ng/μL")
    target_molarity = inputs.numeric.FloatInputField("Target Molarity (nM)", required=False, ge=0.0, unit="nM")
    total_volume_ul = inputs.numeric.FloatInputField("Total Volume (µL)", required=False, ge=0.0, unit="μL")


class LoadFlowCellSeparateAction(HTMXForm):
    template_path = "actions/load-flow-cell-separate.html"

    fields = inputs.dynamic.SubFormList[LaneSubForm](min_elements=1)

    def __init__(self, experiment: models.Experiment) -> None:
        super().__init__()
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity
        self._context["enumerate"] = enumerate
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", experiment_id=experiment.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ) -> "LoadFlowCellSeparateAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
                orm.selectinload(models.Experiment.lanes)
            ))
            if experiment.workflow.combined_lanes:
                raise exc.BadRequestException("This experiment uses a combined lane workflow, not a separate lane workflow.")
            form = cls(experiment=experiment)
            # The table is also needed to re-render the form after a failed submit
            form._prepare(session, prefill=ctx.request.method == "GET")
            return form
        return dependency

    def _prepare(self, session: SyncSession, prefill: bool) -> None:
        lane_table = session.get_pandas(
            Q.pd.experiment_lanes(self.experiment.id),
            limit=None,
        )
        lane_table["library_volume"] = None
        lane_table["eb_volume"] = None

        for idx, row in parsing.safe_iter(lane_table, LaneRowSchema):
            total_volume_ul = row.total_volume_ul if row.total_volume_ul is not None else self.experiment.workflow.volume_target_ul
            if row.target_molarity is not None and row.lane_molarity is not None:
                library_volume = total_volume_ul * row.target_molarity / row.lane_molarity
                lane_table.at[idx, "library_volume"] = library_volume
                lane_table.at[idx, "eb_volume"] = total_volume_ul - library_volume

            if not prefill:
                continue
            entry = self.fields.append_entry()
            entry.lane_id.data = int(row.id)
            entry.total_volume_ul.data = total_volume_ul
            if row.sequencing_qubit_concentration is not None:
                entry.measured_qubit.data = row.sequencing_qubit_concentration
            if row.target_molarity is not None:
                entry.target_molarity.data = row.target_molarity
            if row.phi_x is not None:
                entry.phi_x.data = row.phi_x

        self._context["df"] = lane_table

    def get_context(self) -> dict:
        context = super().get_context()
        # Pair lane rows with their sub-forms (posted entries after a failed submit)
        entries = {str(entry.lane_id.data): entry for entry in self.fields}
        context["rows"] = [(row, entries.get(str(row["id"]))) for _, row in context["df"].iterrows()]
        return context

    @htmx_route("GET", "/{experiment_id}/load-flow-cell/separate")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LoadFlowCellSeparateAction" = Depends(LoadFlowCellSeparateAction.Init()),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/load-flow-cell/separate")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LoadFlowCellSeparateAction" = Depends(LoadFlowCellSeparateAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            for entry in form.fields:
                lane = session.first(Q.lane.select(id=entry.lane_id.data))
                # Only this experiment's lanes (the access check covered this experiment only)
                if lane is None or lane.experiment_id != form.experiment.id:
                    raise exc.NotFoundException(f"Lane with id {entry.lane_id.data} not found in this experiment.")
                lane.target_molarity = entry.target_molarity.data
                lane.total_volume_ul = entry.total_volume_ul.data
                lane.sequencing_qubit_concentration = entry.measured_qubit.data
                lane.phi_x = entry.phi_x.data
                if lane.total_volume_ul is not None and lane.target_molarity is not None and lane.original_molarity is not None:
                    lane.library_volume_ul = lane.total_volume_ul * lane.target_molarity / lane.original_molarity  # type: ignore
                session.save(lane)

            # As legacy: LOADED once every lane of the experiment is loaded (not only the posted ones)
            all_lanes_loaded = all(lane.is_loaded() for lane in form.experiment.lanes)
            if all_lanes_loaded:
                form.experiment.status = C.ExperimentStatus.LOADED
                session.save(form.experiment)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Saved!", "success"),
            )
        return route