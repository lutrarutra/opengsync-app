from fastapi import Depends
from sqlalchemy import orm
import sqlalchemy as sa

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc, responses
from ....components import inputs
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm

class LaneSubForm(SubHTMXForm):
    lane_id = inputs.numeric.IntInputField("Lane ID", required=True, read_only=True)
    lane_num = inputs.numeric.IntInputField("Lane Number", required=True, read_only=True)
    num_m_reads = inputs.numeric.FloatInputField("Number of M Reads", required=False, ge=0.0)

class PoolSubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID", required=True, read_only=True)
    pool_name = inputs.string.StringInputField("Pool Name", required=True, read_only=True)
    lane_forms = inputs.dynamic.SubFormList[LaneSubForm](min_elements=1)

class DistributeReadsSeparateAction(HTMXForm):
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
        ) -> "DistributeReadsSeparateAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
                orm.selectinload(models.Experiment.pools).selectinload(models.Pool.lane_links).selectinload(models.links.LanePoolLink.lane)
            ))
            if experiment.workflow.combined_lanes:
                raise exc.OpeNGSyncServerException("This experiment uses a combined lane workflow, not a separate lane workflow.")
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "{experiment_id}")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "DistributeReadsSeparateAction" = Depends(DistributeReadsSeparateAction.Init()),
        ):
            for pool in form.experiment.pools:
                sub_form = form.pool_forms.append_entry()
                sub_form.pool_id.data = pool.id
                sub_form.pool_name.data = pool.name
                for link in pool.lane_links:
                    lane_form = sub_form.lane_forms.append_entry()
                    lane_form.lane_id.data = link.lane.id
                    lane_form.lane_num.data = link.lane.number
                    lane_form.num_m_reads.data = link.num_m_reads
            return form.make_response()
        return route

    @htmx_route("POST", "{experiment_id}")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "DistributeReadsSeparateAction" = Depends(DistributeReadsSeparateAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            for pool_form in form.pool_forms.entries:
                pool = session.get_one(Q.pool.select(id=pool_form.pool_id.data))
                if pool.experiment_id != form.experiment.id:
                    raise exc.OpeNGSyncServerException(f"Pool {pool.id} does not belong to experiment {form.experiment.id}.")
                
                for lane_form in pool_form.lane_forms.entries:
                    link: models.links.LanePoolLink = session.get_one(sa.Select(models.links.LanePoolLink).where(
                        models.links.LanePoolLink.pool_id == pool.id,
                        models.links.LanePoolLink.lane_id == lane_form.lane_id.data
                    ))
                    link.num_m_reads = lane_form.num_m_reads.data
            
            
            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Reads distributed successfully.", "success")
            )
        return route