from fastapi import Depends

from opengsync_db import models, queries as Q, SyncSession

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class SetExperimentCyclesAction(HTMXForm):
    template_path = "actions/edit-experiment-cycles.html"

    cycles_r1 = inputs.numeric.IntInputField("R1 Cycles", required=False, ge=0)
    cycles_r2 = inputs.numeric.IntInputField("R2 Cycles", required=False, ge=0)
    cycles_i1 = inputs.numeric.IntInputField("I1 Cycles", required=False, ge=0)
    cycles_i2 = inputs.numeric.IntInputField("I2 Cycles", required=False, ge=0)

    def __init__(self, experiment: models.Experiment) -> None:
        super().__init__()
        self.experiment = experiment
        self._context["experiment"] = experiment
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", experiment_id=experiment.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SetExperimentCyclesAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id))
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "/{experiment_id}/cycles")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "SetExperimentCyclesAction" = Depends(SetExperimentCyclesAction.Init()),
        ):
            form.cycles_r1.data = form.experiment.r1_cycles
            form.cycles_r2.data = form.experiment.r2_cycles
            form.cycles_i1.data = form.experiment.i1_cycles
            form.cycles_i2.data = form.experiment.i2_cycles
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/cycles")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SetExperimentCyclesAction" = Depends(SetExperimentCyclesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            form.experiment.r1_cycles = form.cycles_r1.data
            form.experiment.r2_cycles = form.cycles_r2.data
            form.experiment.i1_cycles = form.cycles_i1.data
            form.experiment.i2_cycles = form.cycles_i2.data
            session.save(form.experiment)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id).include_query_params(tab="checklist-tab"),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route