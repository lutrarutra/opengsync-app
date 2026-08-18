from fastapi import Depends
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, actions

from ...core import dependencies, exceptions as exc, responses
from ...utils import parsing
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, HTMXForm, htmx_route
from ..SubHTMXForm import SubHTMXForm

class SubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID")
    qubit_after_dilution = inputs.numeric.FloatInputField("Qubit After Dilution (ng/µL)", ge=0.0)

class DilutePoolsAction(HTMXForm):
    template_path = "actions/dilute-pools.html"
    pool_forms = inputs.dynamic.SubFormList[SubForm](min_elements=1)
    target_total_volume = inputs.numeric.FloatInputField("Target Total Volume (µL)", required=True, default=50, ge=0.0)
    target_molarity = inputs.numeric.FloatInputField("Target Molarity (nM)", required=True, default=3.0, ge=0.0)

    def __init__(self, experiment: models.Experiment) -> None:
        super().__init__()
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["dilute_pools_form"] = self
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", experiment_id=experiment.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "DilutePoolsAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id))
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "/{experiment_id}")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "DilutePoolsAction" = Depends(DilutePoolsAction.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            df = session.pd.get_experiment_pools(form.experiment.id)
            df["molarity_color"] = "cemm-green"
            df.loc[(df["molarity"] < models.Pool.warning_min_molarity) | (models.Pool.warning_max_molarity < df["molarity"]), "molarity_color"] = "cemm-yellow"
            df.loc[(df["molarity"] < models.Pool.error_min_molarity) | (models.Pool.error_max_molarity < df["molarity"]), "molarity_color"] = "cemm-red"

            class RowSchema(BaseModel):
                id: int

            for _, row in parsing.safe_iter(df, RowSchema):
                entry = form.pool_forms.append_entry()
                entry.pool_id.data = row.id

            form._context["df"] = df
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "DilutePoolsAction" = Depends(DilutePoolsAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            for entry in form.pool_forms.entries:
                if entry.qubit_after_dilution.data is None:
                    continue
                
                pool = session.get_one(Q.pool.select(id=int(entry.pool_id.data)))
                if pool.experiment_id != form.experiment.id:
                    raise exc.BadRequestException(f"Pool {pool.name} is not linked to the experiment")
                
                actions.dilute_pool(
                    session, pool=pool,
                    qubit_concentration=entry.qubit_after_dilution.data,
                    operator_id=current_user.id
                )
            
            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id).include_query_params(tab="dilutions-tab"),
                flash=responses.flash("Pools diluted!", "success")
            )
        return route
