from flask import Blueprint, jsonify
from sqlalchemy import orm

from opengsync_db.categories import ExperimentStatus, LibraryStatus
from opengsync_db import models, queries as Q

from ...core import wrappers, exceptions
from ... import db


stats_api_bp = Blueprint("stats_api", __name__, url_prefix="/api/stats/")

@wrappers.api_route(stats_api_bp, db=db, methods=["POST"], json_params=["library_id", "experiment_name", "lane", "num_reads", "qc"])
def set_library_lane_reads(
    library_id: int | None, experiment_name: str, lane: int,
    num_reads: int, qc: dict | None = None, 
):
    if (experiment := db.session.first(Q.experiment.select(name=experiment_name), options=[orm.selectinload(models.Experiment.libraries)])) is None:
        raise exceptions.NotFoundException(f"Experiment with name '{experiment_name}' not found.")
    
    if library_id is not None:
        if (library := db.session.first(Q.library.select(id=library_id, experiment_id=experiment.id))) is None:
            raise exceptions.NotFoundException(f"Library with id '{library_id}' not found in experiment '{experiment_name}'.")
    else:
        library = None
    
    db.actions.set_library_seq_quality(
        library=library if library is not None else None,
        experiment=experiment,
        lane=lane,
        num_reads=num_reads,
        qc=qc
    )

    all_libraries_demultiplexed = True
    for library in experiment.libraries:
        if library.status >= LibraryStatus.SEQUENCED and not library.read_qualities:
            if library.id != library_id:  # current library is being updated, so we can skip the check for read_qualities
                all_libraries_demultiplexed = False
                break
        
    if all_libraries_demultiplexed and experiment.status < ExperimentStatus.DEMULTIPLEXED:
        experiment.status = ExperimentStatus.DEMULTIPLEXED
        db.session.save(experiment)
    
    return jsonify({"status": "success"})
