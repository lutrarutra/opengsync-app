import math
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from ...categories import SequencerModelEnum
from ..DBBlueprint import DBBlueprint
from .. import exceptions


class SequencerBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, name: str,
        model: SequencerModelEnum,
        ip: Optional[str] = None,
        flush: bool = True
    ) -> models.Sequencer:
        if self.db.session.query(models.Sequencer).where(
            models.Sequencer.name == name
        ).first() is not None:
            raise exceptions.NotUniqueValue(f"Sequencer with name '{name}' already exists.")
        
        sequencer = models.Sequencer(
            name=name.strip(),
            model_id=model.id,
            ip=ip.strip() if ip else None
        )

        self.db.session.add(sequencer)

        if flush:
            self.db.flush()
        return sequencer

    @DBBlueprint.transaction
    def get(self, sequencer_id: int) -> models.Sequencer | None:
        sequencer = self.db.session.get(models.Sequencer, sequencer_id)
        return sequencer

    @DBBlueprint.transaction
    def find(
        self,
        name: str | None = None,
        id: int | None = None,
        model_in: list[SequencerModelEnum] | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        page: int | None = None,
    ) -> tuple[list[models.Sequencer], int | None]:
        query = self.db.session.query(models.Sequencer)
        if model_in is not None:
            model_ids = [model.id for model in model_in]
            query = query.where(models.Sequencer.model_id.in_(model_ids))

        if sort_by is not None:
            attr = getattr(models.Sequencer, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if name is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.Sequencer.name, name).desc()))
        if id is not None:
            query = query.where(models.Sequencer.id == id)

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        sequencers = query.all()
        return sequencers, n_pages

    @DBBlueprint.transaction
    def count(self) -> int:
        count = self.db.session.query(models.Sequencer).count()
        return count

    @DBBlueprint.transaction
    def update(self, sequencer: models.Sequencer):
        self.db.session.add(sequencer)

    @DBBlueprint.transaction
    def get_with_name(self, name: str) -> models.Sequencer | None:
        sequencer = self.db.session.query(models.Sequencer).where(
            models.Sequencer.name == name
        ).first()
        return sequencer

    @DBBlueprint.transaction
    def delete(self, sequencer_id: int, flush: bool = True):
        sequencer = self.db.session.get(models.Sequencer, sequencer_id)
        if not sequencer:
            raise exceptions.ElementDoesNotExist(f"Sequencer with id {sequencer_id} does not exist")
        
        if self.db.session.query(models.Experiment).where(
            models.Experiment.sequencer_id == sequencer_id
        ).first() is not None:
            raise exceptions.ElementIsReferenced(f"Sequencer with id {sequencer_id} is referenced by an experiment.")
        
        self.db.session.delete(sequencer)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def query(
        self, word: str, limit: int | None = PAGE_LIMIT
    ) -> list[models.Sequencer]:
        query = self.db.session.query(models.Sequencer).order_by(
            sa.func.similarity(
                models.Sequencer.name, word
            ).desc()
        )

        if limit is not None:
            query = query.limit(limit)

        res = query.all()
        return res

    @DBBlueprint.transaction
    def __getitem__(self, sequencer_id: int) -> models.Sequencer:
        sequencer = self.db.session.get(models.Sequencer, sequencer_id)
        if not sequencer:
            raise exceptions.ElementDoesNotExist(f"Sequencer with id {sequencer_id} does not exist")
        return sequencer

        