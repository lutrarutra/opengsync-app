import sqlalchemy as sa
from sqlalchemy import event, Connection
from sqlalchemy import orm
from sqlalchemy.orm.base import NEVER_SET, NO_VALUE

from .. import models, categories as C

@event.listens_for(models.Library, "after_delete")
def after_library_delete(mapper: orm.Mapper, connection: Connection, target: models.Library):
    # delete orphan samples
    connection.execute(
        sa.delete(models.Sample).where(
            ~sa.exists().where(models.links.SampleLibraryLink.sample_id == models.Sample.id)
        )
    )

    # delete orphan features
    connection.execute(sa.delete(models.Feature).where(
        models.Feature.feature_kit_id.is_(None),
        ~sa.exists().where(models.links.LibraryFeatureLink.feature_id == models.Feature.id)
    ))


@event.listens_for(models.FeatureKit, "after_delete")
def after_feature_kit_delete(mapper: orm.Mapper, connection: Connection, target: models.FeatureKit):
    # delete orphan features
    connection.execute(sa.delete(models.Feature).where(
        models.Feature.feature_kit_id == target.id,
        ~sa.exists().where(models.links.LibraryFeatureLink.feature_id == models.Feature.id)
    ))


@event.listens_for(models.SeqRequest, "after_delete")
def after_seq_request_delete(mapper: orm.Mapper, connection: Connection, target: models.SeqRequest):
    for pool in target.pools:
        if pool.type == C.PoolType.EXTERNAL:
            connection.execute(sa.delete(models.Pool).where(models.Pool.id == pool.id))

@event.listens_for(models.Experiment.workflow_id, "set")
def on_experiment_workflow_changed(target: models.Experiment, value: int, oldvalue: int, initiator):
    if oldvalue is NEVER_SET or oldvalue is NO_VALUE:
        return
    if value == oldvalue:
        return

    workflow = C.ExperimentWorkFlow.get(value)
    if workflow is None:
        return

    new_num_lanes = workflow.flow_cell_type.num_lanes

    if len(target.lanes) > new_num_lanes:
        target.lanes = [_l for _l in target.lanes if _l.number <= new_num_lanes]
        if target.laned_pool_links:
            target.laned_pool_links = [_link for _link in target.laned_pool_links if _link.lane_num <= new_num_lanes]

    elif len(target.lanes) < new_num_lanes:
        current_lane_nums = {lane.number for lane in target.lanes}
        for lane_num in range(1, new_num_lanes + 1):
            if lane_num in current_lane_nums:
                continue
            target.lanes.append(models.Lane(number=lane_num))
        
    if workflow.combined_lanes:
        lps = set([(link.lane_num, link.pool_id) for link in target.laned_pool_links])
        for lane in target.lanes:
            for pool in target.pools:
                if (lane.number, pool.id) not in lps:
                    target.laned_pool_links.append(
                        models.links.LanePoolLink(
                            lane=lane, pool=pool, experiment_id=target.id, lane_num=lane.number
                        )
                    )

    if len(target.lanes) != new_num_lanes:
        raise ValueError(f"Experiment {target.id} has {len(target.lanes)} lanes, but workflow {workflow.name} requires {workflow.flow_cell_type.num_lanes} lanes.")
    if workflow.combined_lanes:
        if len(target.laned_pool_links) != len(target.lanes) * len(target.pools):
            raise ValueError(f"Experiment {target.id} with workflow {workflow.name} requires all lanes to be linked to all pools.")

