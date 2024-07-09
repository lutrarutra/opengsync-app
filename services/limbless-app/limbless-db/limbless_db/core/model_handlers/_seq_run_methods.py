import math
from typing import Optional

import sqlalchemy as sa


from ...models import SeqRun
from ... import PAGE_LIMIT
from ...categories import ReadTypeEnum, RunStatusEnum


def create_seq_run(
    self, experiment_name: str, status: RunStatusEnum, instrument_name: str,
    run_folder: str, flowcell_id: str, read_type: ReadTypeEnum,
    rta_version: str, recipe_version: Optional[str], side: Optional[str], flowcell_mode: Optional[str],
    r1_cycles: Optional[int], i1_cycles: Optional[int], r2_cycles: Optional[int], i2_cycles: Optional[int],
    cluster_count_m: Optional[float] = None, cluster_count_m_pf: Optional[float] = None,
    error_rate: Optional[float] = None, first_cycle_intensity: Optional[float] = None,
    percent_aligned: Optional[float] = None, percent_q30: Optional[float] = None,
    percent_occupied: Optional[float] = None, projected_yield: Optional[float] = None,
    reads_m: Optional[float] = None, reads_m_pf: Optional[float] = None, yield_g: Optional[float] = None
) -> SeqRun:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_run = SeqRun(
        experiment_name=experiment_name.strip(),
        status_id=status.id,
        instrument_name=instrument_name.strip(),
        run_folder=run_folder.strip(),
        flowcell_id=flowcell_id.strip(),
        read_type_id=read_type.id,
        rta_version=rta_version.strip(),
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

    self._session.add(seq_run)

    self._session.commit()
    self._session.refresh(seq_run)

    if not persist_session:
        self.close_session()

    return seq_run


def get_seq_run(self, id: Optional[int] = None, experiment_name: Optional[str] = None) -> Optional[SeqRun]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if id is not None and experiment_name is None:
        seq_run = self._session.get(SeqRun, id)

    elif experiment_name is not None and id is None:
        seq_run = self._session.query(SeqRun).where(
            SeqRun.experiment_name == experiment_name
        ).first()
    else:
        raise ValueError("Either 'id' or 'experiment_name' must be provided.")

    if not persist_session:
        self.close_session()

    return seq_run


def get_seq_runs(
    self,
    status: Optional[RunStatusEnum] = None,
    status_in: Optional[list[RunStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[SeqRun], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(SeqRun)

    if status is not None:
        query = query.where(SeqRun.status_id == status.id)

    if status_in is not None:
        query = query.where(SeqRun.status_id.in_([s.id for s in status_in]))

    if sort_by is not None:
        attr = getattr(SeqRun, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    seq_runs = query.limit(limit).offset(offset).all()

    if not persist_session:
        self.close_session()

    return seq_runs, n_pages


def update_seq_run(
    self, seq_run: SeqRun,
) -> SeqRun:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    self._session.add(seq_run)
    self._session.commit()
    self._session.refresh(seq_run)

    if not persist_session:
        self.close_session()

    return seq_run


def query_seq_runs(self, word: str, limit: Optional[int] = PAGE_LIMIT) -> list[SeqRun]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(SeqRun)
    
    query = query.order_by(
        sa.func.similarity(SeqRun.experiment_name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    seq_runs = query.all()

    if not persist_session:
        self.close_session()

    return seq_runs