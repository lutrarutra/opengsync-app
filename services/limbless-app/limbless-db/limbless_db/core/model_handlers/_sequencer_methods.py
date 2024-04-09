import math
from typing import Optional

import sqlalchemy as sa

from ... import models, PAGE_LIMIT
from ...categories import SequencerTypeEnum
from .. import exceptions


def create_sequencer(
    self, name: str,
    type: SequencerTypeEnum,
    ip: Optional[str] = None,
    commit: bool = True
) -> models.Sequencer:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.Sequencer).where(
        models.Sequencer.name == name
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"Sequencer with name '{name}' already exists.")
    
    sequencer = models.Sequencer(
        name=name.strip(),
        type_id=type.id,
        ip=ip.strip() if ip else None
    )

    self._session.add(sequencer)
    if commit:
        self._session.commit()
        self._session.refresh(sequencer)

    if not persist_session:
        self.close_session()

    return sequencer


def get_sequencer(
    self, sequencer_id: int,
) -> models.Sequencer:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sequencer = self._session.get(models.Sequencer, sequencer_id)

    if not persist_session:
        self.close_session()

    return sequencer


def get_sequencers(
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None
) -> tuple[list[models.Sequencer], int]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sequencer)

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    sequencers = query.all()

    if not persist_session:
        self.close_session()

    return sequencers, n_pages


def get_num_sequencers(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    count = self._session.query(models.Sequencer).count()

    if not persist_session:
        self.close_session()

    return count


def update_sequencer(self, sequencer: models.Sequencer) -> models.Sequencer:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
    
    self._session.add(sequencer)
    self._session.commit()
    self._session.refresh(sequencer)

    if not persist_session:
        self.close_session()

    return sequencer


def get_sequencer_by_name(
    self, name: str
) -> models.Sequencer:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sequencer = self._session.query(models.Sequencer).where(
        models.Sequencer.name == name
    ).first()

    if not persist_session:
        self.close_session()

    return sequencer


def delete_sequencer(
    self, sequencer_id: int,
    commit: bool = True
):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sequencer = self._session.get(models.Sequencer, sequencer_id)
    if not sequencer:
        raise exceptions.ElementDoesNotExist(f"Sequencer with id {sequencer_id} does not exist")
    
    if self._session.query(models.Experiment).where(
        models.Experiment.sequencer_id == sequencer_id
    ).first() is not None:
        raise exceptions.ElementIsReferenced(f"Sequencer with id {sequencer_id} is referenced by an experiment.")
    
    self._session.delete(sequencer)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
    

def query_sequencers(
    self, word: str, limit: Optional[int] = PAGE_LIMIT
) -> list[models.Sequencer]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sequencer).order_by(
        sa.func.similarity(
            models.Sequencer.name, word
        ).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res


    