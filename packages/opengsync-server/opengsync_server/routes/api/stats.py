from flask import Blueprint, jsonify
from sqlalchemy import orm

from opengsync_db.categories import ExperimentStatus, LibraryStatus
from opengsync_db import models

from ...core import wrappers, exceptions
from ... import db


stats_api_bp = Blueprint("stats_api", __name__, url_prefix="/api/stats/")

@wrappers.api_route(stats_api_bp, db=db, methods=["POST"], json_params=["library_id", "experiment_name", "lane", "num_reads", "qc"])
def set_library_lane_reads(
    library_id: int | None, experiment_name: str, lane: int,
    num_reads: int, qc: dict | None = None, 
):
    if (experiment := db.experiments.get(experiment_name, options=orm.selectinload(models.Experiment.libraries))) is None:
        raise exceptions.NotFoundException(f"Experiment with name '{experiment_name}' not found.")
    
    db.libraries.set_seq_quality(
        library_id=library_id,
        experiment_id=experiment.id,
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
        db.experiments.update(experiment)
    
    return jsonify({"status": "success"})
