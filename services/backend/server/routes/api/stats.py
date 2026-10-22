from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, actions
from opengsync_db.transitions import run_operation, sequencing as sequencing_ops

from ...core import dependencies, exceptions as exc

router = APIRouter(prefix="/stats", tags=["api", "stats"])


class SetLibraryLaneReadsRequest(BaseModel):
    library_id: int | None = None
    experiment_name: str
    lane: int
    num_reads: int
    qc: dict[str, Any] | None = None


@router.post("/set-library-lane-reads", dependencies=[Depends(dependencies.require_insider)])
def set_library_lane_reads(
    body: SetLibraryLaneReadsRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, str]:
    experiment = session.first(
        Q.experiment.select(name=body.experiment_name),
        options=[orm.selectinload(models.Experiment.libraries).selectinload(models.Library.read_qualities)],
    )
    if experiment is None:
        raise exc.NotFoundException(f"Experiment with name '{body.experiment_name}' not found.")

    library = None
    if body.library_id is not None:
        library = session.first(Q.library.select(id=body.library_id, experiment_id=experiment.id))
        if library is None:
            raise exc.NotFoundException(
                f"Library with id '{body.library_id}' not found in experiment '{body.experiment_name}'."
            )

    with run_operation(session, sequencing_ops.LANE_READS, subject=experiment):
        actions.set_library_seq_quality(
            session,
            library=library,
            experiment=experiment,
            lane=body.lane,
            num_reads=body.num_reads,
            qc=body.qc,
        )

        all_libraries_demultiplexed = True
        for exp_library in experiment.libraries:
            if exp_library.status >= C.LibraryStatus.SEQUENCED and not exp_library.read_qualities and exp_library.id != body.library_id:
                all_libraries_demultiplexed = False
                break

        if all_libraries_demultiplexed and experiment.status < C.ExperimentStatus.DEMULTIPLEXED:
            experiment.status = C.ExperimentStatus.DEMULTIPLEXED
            session.save(experiment, flush=True)

    return {"status": "success"}



class SetQCRequest(BaseModel):
    library_id: int
    sample_id: int | None = None
    qc: dict[str, Any]


@router.post("/set-qc", dependencies=[Depends(dependencies.require_insider)])
def set_qc(
    body: SetQCRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    """Replaces the qc of a library (sample_id=None) or of a sample-library link."""
    target: models.Library | models.links.SampleLibraryLink | None
    if body.sample_id is None:
        if (target := session.first(Q.library.select(id=body.library_id))) is None:
            raise exc.NotFoundException(f"Library with ID '{body.library_id}' not found.")
    else:
        target = session.first(Q.links.get_sample_library_link(sample_id=body.sample_id, library_id=body.library_id))
        if target is None:
            raise exc.NotFoundException(
                f"Sample-library link for sample_id='{body.sample_id}' and library_id='{body.library_id}' not found."
            )

    target.qc = body.qc or None
    session.save(target)

    return {"result": "success", "qc": target.qc or {}}
