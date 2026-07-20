from fastapi import Depends
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ....components import inputs
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm


class PoolSubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID", required=True, read_only=True)
    pool_name = inputs.string.StringInputField("Pool Name", required=True, read_only=True)
    num_reads = inputs.numeric.FloatInputField("Number of Reads", required=False, ge=0.0)

class DistributeReadsCombinedAction(HTMXForm):
    pool_forms = inputs.dynamic.SubFormList[PoolSubForm](min_elements=1)

    def __init__(self, experiment: models.Experiment) -> None:
        super().__init__()
        self.experiment = experiment
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", experiment_id=experiment.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider)
        ) -> "DistributeReadsCombinedAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
                orm.selectinload(models.Experiment.pools).selectinload(models.Pool.lane_links).selectinload(models.links.LanePoolLink.lane)
            ))
            if experiment.status != C.ExperimentStatus.DRAFT and not current_user.is_admin:
                raise exc.NoPermissionsException("Only admin can edit non-draft experiments")
            
            if not experiment.workflow.combined_lanes:
                raise exc.OpeNGSyncServerException("This experiment uses a separate lane workflow, not a combined lane workflow.")
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "{experiment_id}")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "DistributeReadsCombinedAction" = Depends(DistributeReadsCombinedAction.Init()),
        ):
            for pool in form.experiment.pools:
                sub_form = form.pool_forms.append_entry()
                sub_form.pool_id.data = pool.id
                sub_form.pool_name.data = pool.name
                sub_form.num_reads.data = pool.lane_links[0].num_m_reads * form.experiment.num_lanes if pool.lane_links[0].num_m_reads is not None else None
                
            return form.make_response()
        return route

    @htmx_route("POST", "{experiment_id}")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "DistributeReadsCombinedAction" = Depends(DistributeReadsCombinedAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            links: dict[tuple[int, int], models.links.LanePoolLink] = {}
            for link in form.experiment.laned_pool_links:
                links[(link.lane_id, link.pool_id)] = link

            for pool_field in form.pool_forms:
                if pool_field.num_reads.data is None:
                    continue
                
                pool = session.get_one(Q.pool.select(id=pool_field.pool_id.data).options(orm.selectinload(models.Pool.lane_links)))
                
                for link in pool.lane_links:
                    link.num_m_reads = pool_field.num_reads.data / form.experiment.num_lanes
                
            
            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Reads distributed successfully.", "success")
            )
        return route