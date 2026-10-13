from fastapi import Depends
from sqlalchemy import orm
import sqlalchemy as sa

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ....components import inputs
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm


class LaneReadsSubForm(SubHTMXForm):
    """Reads of one pool on one lane (one flat list; sub-form lists cannot be nested)."""
    pool_id = inputs.numeric.IntInputField("Pool ID", required=True, read_only=True, hidden=True)
    lane_id = inputs.numeric.IntInputField("Lane ID", required=True, read_only=True, hidden=True)
    num_m_reads = inputs.numeric.FloatInputField("Number of M Reads", required=False, ge=0.0, unit="M")


class DistributeReadsSeparateAction(HTMXForm):
    template_path = "actions/distribute-reads-separate.html"
    read_forms = inputs.dynamic.SubFormList[LaneReadsSubForm](min_elements=1)

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
            current_user: models.User = Depends(dependencies.require_insider),
        ) -> "DistributeReadsSeparateAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
                orm.selectinload(models.Experiment.pools).selectinload(models.Pool.lane_links).selectinload(models.links.LanePoolLink.lane)
            ))
            if experiment.status != C.ExperimentStatus.DRAFT and not current_user.is_admin:
                raise exc.NoPermissionsException("Only admin can edit non-draft experiments")

            if experiment.workflow.combined_lanes:
                raise exc.BadRequestException("This experiment uses a combined lane workflow, not a separate lane workflow.")
            return cls(experiment=experiment)
        return dependency

    def get_context(self) -> dict:
        context = super().get_context()
        # One row per pool, one cell per lane: the pool's entry for that lane, if it is on it
        entries = {(str(entry.pool_id.data), str(entry.lane_id.data)): entry for entry in self.read_forms}
        lanes = sorted(self.experiment.lanes, key=lambda lane: lane.number)
        context["lanes"] = lanes
        context["pool_rows"] = [
            (pool, [entries.get((str(pool.id), str(lane.id))) for lane in lanes])
            for pool in self.experiment.pools
        ]
        return context

    @htmx_route("GET", "/{experiment_id}/distribute-reads/separate")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "DistributeReadsSeparateAction" = Depends(DistributeReadsSeparateAction.Init()),
        ):
            for pool in form.experiment.pools:
                for link in pool.lane_links:
                    entry = form.read_forms.append_entry()
                    entry.pool_id.data = pool.id
                    entry.lane_id.data = link.lane.id
                    entry.num_m_reads.data = link.num_m_reads
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/distribute-reads/separate")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "DistributeReadsSeparateAction" = Depends(DistributeReadsSeparateAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            for entry in form.read_forms:
                link = session.first(sa.Select(models.links.LanePoolLink).where(
                    models.links.LanePoolLink.experiment_id == form.experiment.id,
                    models.links.LanePoolLink.pool_id == entry.pool_id.data,
                    models.links.LanePoolLink.lane_id == entry.lane_id.data,
                ))
                if link is None:
                    raise exc.NotFoundException(f"Pool {entry.pool_id.data} is not on lane {entry.lane_id.data} of this experiment.")
                # As legacy: an empty cell clears the lane's reads
                link.num_m_reads = entry.num_m_reads.data

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Reads distributed successfully.", "success")
            )
        return route
