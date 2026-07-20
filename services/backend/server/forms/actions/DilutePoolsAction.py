from fastapi import Depends

from opengsync_db import models, queries as Q, SyncSession, actions

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, HTMXForm, htmx_route
from ..SubHTMXForm import SubHTMXForm

class SubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID")
    qubit_after_dilution = inputs.numeric.FloatInputField("Qubit After Dilution (ng/µL)", ge=0.0)

class DilutePoolsAction(HTMXForm):
    pool_forms = inputs.dynamic.SubFormList[SubForm](min_elements=1)
    target_total_volume = inputs.numeric.FloatInputField("Target Total Volume (µL)", required=True, default=50, ge=0.0)
    target_molarity = inputs.numeric.FloatInputField("Target Molarity (nM)", required=True, default=3.0, ge=0.0)


    @htmx_route("GET", "/{experiment_id}")
    def Begin(cls) -> RouteFunc:
        def route(
            experiment_id: int,
            form: "DilutePoolsAction" = Depends(DilutePoolsAction.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            df = session.pd.get_experiment_pools(experiment_id)
            df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
            df["molarity_color"] = "cemm-green"
            df.loc[(df["molarity"] < models.Pool.warning_min_molarity) | (models.Pool.warning_max_molarity < df["molarity"]), "molarity_color"] = "cemm-yellow"
            df.loc[(df["molarity"] < models.Pool.error_min_molarity) | (models.Pool.error_max_molarity < df["molarity"]), "molarity_color"] = "cemm-red"

            for _, row in df.iterrows():
                entry = form.pool_forms.append_entry()
                entry.pool_id.data = row["id"]
                
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}")
    def Submit(cls) -> RouteFunc:
        def route(
            experiment_id: int,
            form: "DilutePoolsAction" = Depends(DilutePoolsAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            experiment = session.get_one(Q.experiment.select(id=experiment_id))
            
            for entry in form.pool_forms.entries:
                if entry.qubit_after_dilution.data is None:
                    continue
                
                pool = session.get_one(Q.pool.select(id=int(entry.pool_id.data)))
                if pool.experiment_id != experiment.id:
                    raise exc.BadRequestException(f"Pool {pool.name} is not linked to the experiment")
                
                actions.dilute_pool(
                    session, pool=pool,
                    qubit_concentration=entry.qubit_after_dilution.data,
                    operator_id=current_user.id
                )
            
            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=experiment.id).include_query_params(tab="dilutions-tab"),
                flash=responses.flash(f"Pools diluted!", "success")
            )
        return route