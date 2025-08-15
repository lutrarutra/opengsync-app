import math
from typing import Optional, TYPE_CHECKING, Callable

import sqlalchemy as sa
from sqlalchemy.orm import Query

if TYPE_CHECKING:
    from ..units import Quantity

from ..DBBlueprint import DBBlueprint
from ... import models, PAGE_LIMIT
from ...categories import ReadTypeEnum, RunStatusEnum, ExperimentStatusEnum


class SeqRunBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        status: Optional[RunStatusEnum] = None,
        status_in: Optional[list[RunStatusEnum]] = None,
        experiment_status: Optional[ExperimentStatusEnum] = None,
        experiment_status_in: Optional[list[ExperimentStatusEnum]] = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:

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

        if custom_query is not None:
            query = custom_query(query)

        return query

    @DBBlueprint.transaction
    def create(
        self, experiment_name: str, status: RunStatusEnum, instrument_name: str,
        run_folder: str, flowcell_id: str, read_type: ReadTypeEnum,
        r1_cycles: Optional[int], i1_cycles: Optional[int], r2_cycles: Optional[int], i2_cycles: Optional[int],
        quantities: Optional[dict[str, "Quantity"]] = None, rta_version: Optional[str] = None, recipe_version: Optional[str] = None,
        side: Optional[str] = None, flowcell_mode: Optional[str] = None,
        flush: bool = True
    ) -> models.SeqRun:
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
        )

        if quantities is not None:
            for key, value in quantities.items():
                seq_run.set_quantity(key, value)

        self.db.session.add(seq_run)

        if flush:
            self.db.flush()
        return seq_run

    @DBBlueprint.transaction
    def get(self, id: int | None = None, experiment_name: Optional[str] = None) -> models.SeqRun | None:
        if id is not None and experiment_name is None:
            seq_run = self.db.session.get(models.SeqRun, id)

        elif experiment_name is not None and id is None:
            seq_run = self.db.session.query(models.SeqRun).where(
                models.SeqRun.experiment_name == experiment_name
            ).first()
        else:
            raise ValueError("Either 'id' or 'experiment_name' must be provided.")
        return seq_run

    @DBBlueprint.transaction
    def find(
        self,
        status: Optional[RunStatusEnum] = None,
        status_in: Optional[list[RunStatusEnum]] = None,
        experiment_status: Optional[ExperimentStatusEnum] = None,
        experiment_status_in: Optional[list[ExperimentStatusEnum]] = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.SeqRun], int | None]:
        query = self.db.session.query(models.SeqRun)
        query = SeqRunBP.where(
            query,
            status=status,
            status_in=status_in,
            experiment_status=experiment_status,
            experiment_status_in=experiment_status_in,
            custom_query=custom_query
        )
        
        if sort_by is not None:
            attr = getattr(models.SeqRun, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        seq_runs = query.limit(limit).offset(offset).all()
        return seq_runs, n_pages

    @DBBlueprint.transaction
    def update(self, seq_run: models.SeqRun):
        self.db.session.add(seq_run)

    @DBBlueprint.transaction
    def query(self, word: str, limit: int | None = PAGE_LIMIT) -> list[models.SeqRun]:
        query = self.db.session.query(models.SeqRun)
        query = query.order_by(
            sa.func.similarity(models.SeqRun.experiment_name, word).desc()
        )

        if limit is not None:
            query = query.limit(limit)

        seq_runs = query.all()
        return seq_runs