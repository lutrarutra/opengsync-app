import pandas as pd
from fastapi import Depends
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, actions

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import dependencies, exceptions as exc, responses
from ...core.context import ctx
from ...utils import parsing
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, HTMXForm, htmx_route
from ..SubHTMXForm import SubHTMXForm

class SubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID", hidden=True, read_only=True)
    # As legacy: optional, pools left empty are not diluted
    qubit_after_dilution = inputs.numeric.FloatInputField("Qubit After Dilution (ng/µL)", required=False, ge=0.0, unit="ng/μL")

class DilutePoolsAction(HTMXForm):
    template_path = "actions/dilute-pools.html"
    pool_forms = inputs.dynamic.SubFormList[SubForm](min_elements=1)
    target_total_volume = inputs.numeric.FloatInputField("Target Total Volume (µL)", required=True, default=50, ge=0.0, unit="μL")
    target_molarity = inputs.numeric.FloatInputField("Target Molarity (nM)", required=True, default=3.0, ge=0.0, unit="nM")

    def __init__(self, experiment: models.Experiment) -> None:
        super().__init__()
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", experiment_id=experiment.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> "DilutePoolsAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id))
            form = cls(experiment=experiment)
            # As legacy: the pool table is also needed to re-render the form after a failed submit
            form._prepare(session, prefill=ctx.request.method == "GET")
            return form
        return dependency

    def _prepare(self, session: SyncSession, prefill: bool) -> None:
        df = T.experiment_pools(
            session.get_pandas(
                Q.pd.experiment_pools(self.experiment.id),
                limit=None,
            )
        )
        df["molarity"] = pd.to_numeric(df["molarity"], errors="coerce").astype(float)
        df["molarity_color"] = "cemm-green"
        df.loc[(df["molarity"] < models.Pool.warning_min_molarity) | (models.Pool.warning_max_molarity < df["molarity"]), "molarity_color"] = "cemm-yellow"
        df.loc[(df["molarity"] < models.Pool.error_min_molarity) | (models.Pool.error_max_molarity < df["molarity"]), "molarity_color"] = "cemm-red"

        class RowSchema(BaseModel):
            id: int

        if prefill:
            for _, row in parsing.safe_iter(df, RowSchema):
                entry = self.pool_forms.append_entry()
                entry.pool_id.data = row.id

        self._context["df"] = df

    def get_context(self) -> dict:
        context = super().get_context()
        # Pair pool rows with their sub-forms (posted entries after a failed submit)
        entries = {str(entry.pool_id.data): entry for entry in self.pool_forms}
        context["rows"] = [(row, entries.get(str(row["id"]))) for _, row in context["df"].iterrows()]
        return context

    @htmx_route("GET", "/{experiment_id}")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "DilutePoolsAction" = Depends(DilutePoolsAction.Init()),
        ):
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
                
                pool = session.first(Q.pool.select(id=int(entry.pool_id.data)))
                if pool is None or pool.experiment_id != form.experiment.id:
                    raise exc.NotFoundException(f"Pool {entry.pool_id.data} not found in this experiment.")
                
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
