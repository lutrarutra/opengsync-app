from flask import Blueprint, jsonify

from opengsync_db.categories import ExperimentStatus

from ...core import wrappers, exceptions
from ... import db


stats_api_bp = Blueprint("stats_api", __name__, url_prefix="/api/stats/")

@wrappers.api_route(stats_api_bp, db=db, methods=["POST"], json_params=["library_id", "experiment_name", "lane", "num_reads", "qc"])
def set_library_lane_reads(
    library_id: int | None, experiment_name: str, lane: int,
    num_reads: int, qc: dict | None = None, 
):
    if (experiment := db.experiments.get(experiment_name)) is None:
        raise exceptions.NotFoundException(f"Experiment with name '{experiment_name}' not found.")
    
    if experiment.status < ExperimentStatus.DEMULTIPLEXED:
        experiment.status = ExperimentStatus.DEMULTIPLEXED
        db.experiments.update(experiment)
    
    db.libraries.set_seq_quality(
        library_id=library_id,
        experiment_id=experiment.id,
        lane=lane,
        num_reads=num_reads,
        qc=qc
    )
    
    return jsonify({"status": "success"})
