import pandas as pd
from fastapi import Depends
from sqlalchemy import orm
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
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
    lane_id = inputs.numeric.IntInputField("Lane ID", required=True, read_only=True)
    phi_x = inputs.numeric.FloatInputField("Phi X %", required=True, ge=0.0)
    measured_qubit = inputs.numeric.FloatInputField("Qubit Concentration After Dilution", required=False, ge=0.0)
    target_molarity = inputs.numeric.FloatInputField("Target Molarity (nM)", required=False, ge=0.0)
    total_volume_ul = inputs.numeric.FloatInputField("Total Volume (µL)", required=False, ge=0.0)


class LoadFlowCellSeparateAction(HTMXForm):
    template_path = "workflows/experiment/load_flow_cell-1.1.html"

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
                raise exc.OpeNGSyncServerException("This experiment uses a combined lane workflow, not a separate lane workflow.")
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "/{experiment_id}/load-flow-cell")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LoadFlowCellSeparateAction" = Depends(LoadFlowCellSeparateAction.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            lane_table = session.pd.get_experiment_lanes(form.experiment.id)
            lane_table["library_volume"] = None
            lane_table["eb_volume"] = None

            for idx, row in parsing.safe_iter(lane_table, LaneRowSchema):
                if pd.notna(row.total_volume_ul):
                    total_volume_ul = row.total_volume_ul
                else:
                    total_volume_ul = form.experiment.workflow.volume_target_ul

                if row.target_molarity is not None and row.lane_molarity is not None:
                    library_volume = total_volume_ul * row.target_molarity / row.lane_molarity
                    lane_table.at[idx, "library_volume"] = library_volume
                    lane_table.at[idx, "eb_volume"] = total_volume_ul - library_volume

            for idx, row in parsing.safe_iter(lane_table, LaneRowSchema):
                entry = form.fields.append_entry()
                entry.lane_id.data = int(row.id)

                if pd.notna(row.total_volume_ul):
                    entry.total_volume_ul.data = row.total_volume_ul
                else:
                    entry.total_volume_ul.data = form.experiment.workflow.volume_target_ul

                if pd.notna(row.sequencing_qubit_concentration):
                    entry.measured_qubit.data = row.sequencing_qubit_concentration

                if row.target_molarity is not None and row.lane_molarity is not None:
                    entry.target_molarity.data = row.target_molarity
                    library_volume = entry.total_volume_ul.data * row.target_molarity / row.lane_molarity
                    lane_table.at[idx, "library_volume"] = library_volume
                    lane_table.at[idx, "eb_volume"] = entry.total_volume_ul.data - library_volume

                if pd.notna(row.phi_x):
                    entry.phi_x.data = row.phi_x

            form._context["df"] = lane_table
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/load-flow-cell")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LoadFlowCellSeparateAction" = Depends(LoadFlowCellSeparateAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            all_lanes_loaded = True
            for entry in form.fields:
                lane = session.get_one(Q.lane.select(id=entry.lane_id.data))
                lane.target_molarity = entry.target_molarity.data
                lane.total_volume_ul = entry.total_volume_ul.data
                lane.sequencing_qubit_concentration = entry.measured_qubit.data
                lane.phi_x = entry.phi_x.data
                if lane.total_volume_ul is not None and lane.target_molarity is not None and lane.original_molarity is not None:
                    lane.library_volume_ul = lane.total_volume_ul * lane.target_molarity / lane.original_molarity  # type: ignore
                session.save(lane)
                all_lanes_loaded = all_lanes_loaded and lane.is_loaded()

            if all_lanes_loaded:
                form.experiment.status = C.ExperimentStatus.LOADED
                session.save(form.experiment)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Saved!", "success"),
            )
        return route