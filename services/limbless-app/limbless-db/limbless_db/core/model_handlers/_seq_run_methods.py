import math
from typing import Optional

from ...models import SeqRun
from ... import PAGE_LIMIT
from ...categories import ReadTypeEnum, ExperimentStatusEnum


def create_seq_run(
    self, experiment_name: str,
    status: ExperimentStatusEnum,
    run_folder: str,
    flowcell_id: str,
    read_type: ReadTypeEnum,
    rta_version: str,
    recipe_version: str,
    side: str,
    flowcell_mode: str,
    r1_cycles: int,
    i1_cycles: int,
    r2_cycles: int,
    i2_cycles: int,
) -> SeqRun:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    seq_run = SeqRun(
        experiment_name=experiment_name,
        status_id=status.id,
        run_folder=run_folder,
        flowcell_id=flowcell_id,
        read_type_id=read_type.id,
        rta_version=rta_version,
        recipe_version=recipe_version,
        side=side,
        flowcell_mode=flowcell_mode,
        r1_cycles=r1_cycles,
        r2_cycles=r2_cycles,
        i1_cycles=i1_cycles,
        i2_cycles=i2_cycles,
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
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
) -> tuple[list[SeqRun], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(SeqRun)

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