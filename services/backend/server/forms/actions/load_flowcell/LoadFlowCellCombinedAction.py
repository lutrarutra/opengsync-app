from fastapi import Depends
from sqlalchemy import orm
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C
from opengsync_db.transitions import run_operation, sequencing as sequencing_ops

from ....core import dependencies, exceptions as exc, responses
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route

class LaneRowSchema(BaseModel):
    total_volume_ul: float | None
    target_molarity: float | None
    lane_molarity: float | None
    sequencing_qubit_concentration: float | None
    sequencing_molarity: float | None
    original_qubit_concentration: float | None
    avg_fragment_size: int | None
    phi_x: float | None
    id: int


class LoadFlowCellCombinedAction(HTMXForm):
    template_path = "actions/load-flow-cell-combined.html"

    phi_x = inputs.numeric.FloatInputField("Phi X %", required=True, ge=0.0, unit="%")
    measured_qubit = inputs.numeric.FloatInputField("Qubit Concentration After Dilution", required=False, ge=0.0, unit="ng/μL")
    target_molarity = inputs.numeric.FloatInputField("Target Molarity (nM)", required=False, ge=0.0, unit="nM")
    total_volume_ul = inputs.numeric.FloatInputField("Total Volume (µL)", required=False, ge=0.0, unit="μL")

    # Display only (as legacy: no validators); the template posts them back with the form
    avg_fragment_size = inputs.numeric.IntInputField("Avg. Fragment Size", required=False, read_only=True, unit="bp")
    qubit_concentration = inputs.numeric.FloatInputField("Qubit Concentration", required=False, read_only=True, unit="ng/μL")
    lane_molarity = inputs.numeric.FloatInputField("Lane Molarity", required=False, read_only=True, unit="nM")
    sequencing_molarity = inputs.numeric.FloatInputField("Sequencing Molarity", required=False, read_only=True, unit="nM")
    library_volume = inputs.numeric.FloatInputField("Library Volume", required=False, read_only=True, unit="μL")
    eb_volume = inputs.numeric.FloatInputField("EB Volume", required=False, read_only=True, unit="μL")

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
        ) -> "LoadFlowCellCombinedAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
                orm.selectinload(models.Experiment.lanes)
            ))
            if not experiment.workflow.combined_lanes:
                raise exc.BadRequestException(
                    "This experiment uses a separate lane workflow, not a combined lane workflow."
                )
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "/{experiment_id}/load-flow-cell/combined")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LoadFlowCellCombinedAction" = Depends(LoadFlowCellCombinedAction.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            df = session.get_pandas(
                Q.pd.experiment_lanes(form.experiment.id),
                limit=None,
            )
            _, row = next(iter(parsing.safe_iter(df, LaneRowSchema)))

            if row.total_volume_ul is not None:
                form.total_volume_ul.data = row.total_volume_ul
            else:
                form.total_volume_ul.data = form.experiment.workflow.volume_target_ul

            if row.sequencing_qubit_concentration is not None:
                form.measured_qubit.data = row.sequencing_qubit_concentration

            if row.target_molarity is not None and row.lane_molarity is not None:
                form.target_molarity.data = row.target_molarity
                library_volume = form.total_volume_ul.data * row.target_molarity / row.lane_molarity
                eb_volume = form.total_volume_ul.data - library_volume
            else:
                library_volume = None
                eb_volume = None

            if row.phi_x is not None:
                form.phi_x.data = row.phi_x

            form.avg_fragment_size.data = row.avg_fragment_size
            form.qubit_concentration.data = row.original_qubit_concentration
            form.lane_molarity.data = row.lane_molarity
            form.sequencing_molarity.data = row.sequencing_molarity
            form.library_volume.data = library_volume
            form.eb_volume.data = eb_volume

            form._context["df"] = df
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/load-flow-cell/combined")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LoadFlowCellCombinedAction" = Depends(LoadFlowCellCombinedAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            loaded = True
            for lane in form.experiment.lanes:
                lane.total_volume_ul = form.total_volume_ul.data
                lane.sequencing_qubit_concentration = form.measured_qubit.data
                lane.target_molarity = form.target_molarity.data
                lane.phi_x = form.phi_x.data
                if (lane_molarity := lane.original_molarity) is not None and lane.target_molarity is not None and lane.total_volume_ul is not None:
                    lane.library_volume_ul = lane.total_volume_ul * lane.target_molarity / lane_molarity  # type: ignore
                else:
                    loaded = False
                session.save(lane)

            with run_operation(session, sequencing_ops.LOAD_FLOWCELL, subject=form.experiment):
                if loaded:
                    form.experiment.status = C.ExperimentStatus.LOADED
                    session.save(form.experiment)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Saved!", "success"),
            )
        return route