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
        self, limit: int | None = PAGE_LIMIT, offset: int | None = None,
        count_pages: bool = False
    ) -> tuple[list[models.Sequencer], int | None]:
        query = self.db.session.query(models.Sequencer)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

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

        