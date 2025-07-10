import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import ReadTypeEnum, RunStatusEnum, ExperimentStatus, ExperimentStatusEnum


def create_seq_run(
    self: "DBHandler", experiment_name: str, status: RunStatusEnum, instrument_name: str,
    run_folder: str, flowcell_id: str, read_type: ReadTypeEnum,
    r1_cycles: Optional[int], i1_cycles: Optional[int], r2_cycles: Optional[int], i2_cycles: Optional[int],
    rta_version: Optional[str] = None, recipe_version: Optional[str] = None, side: Optional[str] = None, flowcell_mode: Optional[str] = None,
    cluster_count_m: Optional[float] = None, cluster_count_m_pf: Optional[float] = None,
    error_rate: Optional[float] = None, first_cycle_intensity: Optional[float] = None,
    percent_aligned: Optional[float] = None, percent_q30: Optional[float] = None,
    percent_occupied: Optional[float] = None, projected_yield: Optional[float] = None,
    reads_m: Optional[float] = None, reads_m_pf: Optional[float] = None, yield_g: Optional[float] = None
) -> models.SeqRun:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    seq_run = models.SeqRun(
        experiment_name=experiment_name.strip(),
        status_id=status.id,
        instrument_name=instrument_name.strip(),
        run_folder=run_folder.strip(),
        flowcell_id=flowcell_id.strip(),
        read_type_id=read_type.id,
        rta_version=rta_version.strip() if rta_version else None,
        recipe_version=recipe_version.strip() if recipe_version else None,
        side=side.strip() if side else None,
        flowcell_mode=flowcell_mode.strip() if flowcell_mode else None,
        r1_cycles=r1_cycles,
        r2_cycles=r2_cycles,
        i1_cycles=i1_cycles,
        i2_cycles=i2_cycles,
        cluster_count_m=cluster_count_m,
        cluster_count_m_pf=cluster_count_m_pf,
        error_rate=error_rate,
        first_cycle_intensity=first_cycle_intensity,
        percent_aligned=percent_aligned,
        percent_q30=percent_q30,
        percent_occupied=percent_occupied,
        projected_yield=projected_yield,
        reads_m=reads_m,
        reads_m_pf=reads_m_pf,
        yield_g=yield_g
    )

    self.session.add(seq_run)

    self.session.commit()
    self.session.refresh(seq_run)

    if not persist_session:
        self.close_session()

    return seq_run


def get_seq_run(self: "DBHandler", id: Optional[int] = None, experiment_name: Optional[str] = None) -> models.SeqRun | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if id is not None and experiment_name is None:
        seq_run = self.session.get(models.SeqRun, id)

    elif experiment_name is not None and id is None:
        seq_run = self.session.query(models.SeqRun).where(
            models.SeqRun.experiment_name == experiment_name
        ).first()
    else:
        raise ValueError("Either 'id' or 'experiment_name' must be provided.")

    if not persist_session:
        self.close_session()

    return seq_run


def get_seq_runs(
    self: "DBHandler",
    status: Optional[RunStatusEnum] = None,
    status_in: Optional[list[RunStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    experiment_status: Optional[ExperimentStatusEnum] = None,
    experiment_status_in: Optional[list[ExperimentStatusEnum]] = None,
    count_pages: bool = False
) -> tuple[list[models.SeqRun], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.SeqRun)

    if status is not None:
        query = query.where(models.SeqRun.status_id == status.id)

    if status_in is not None:
        query = query.where(models.SeqRun.status_id.in_([s.id for s in status_in]))

    if experiment_status is not None or experiment_status_in is not None:
        query = query.join(
            models.Experiment,
            models.Experiment.name == models.SeqRun.experiment_name,
        )

        if experiment_status is not None:
            query = query.where(models.Experiment.status_id == experiment_status.id)
            
        if experiment_status_in is not None:
            query = query.where(models.Experiment.status_id.in_([s.id for s in experiment_status_in]))

    if sort_by is not None:
        attr = getattr(models.SeqRun, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    seq_runs = query.limit(limit).offset(offset).all()

    if not persist_session:
        self.close_session()

    return seq_runs, n_pages


def update_seq_run(
    self: "DBHandler", seq_run: models.SeqRun,
) -> models.SeqRun:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(seq_run)
    self.session.commit()
    self.session.refresh(seq_run)

    if not persist_session:
        self.close_session()

    return seq_run


def query_seq_runs(self: "DBHandler", word: str, limit: Optional[int] = PAGE_LIMIT) -> list[models.SeqRun]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.SeqRun)
    
    query = query.order_by(
        sa.func.similarity(models.SeqRun.experiment_name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    seq_runs = query.all()

    if not persist_session:
        self.close_session()

    return seq_runs