import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import SequencerModelEnum
from .. import exceptions


def create_sequencer(
    self: "DBHandler", name: str,
    model: SequencerModelEnum,
    ip: Optional[str] = None
) -> models.Sequencer:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.query(models.Sequencer).where(
        models.Sequencer.name == name
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"Sequencer with name '{name}' already exists.")
    
    sequencer = models.Sequencer(
        name=name.strip(),
        model_id=model.id,
        ip=ip.strip() if ip else None
    )

    self.session.add(sequencer)
    self.session.commit()
    self.session.refresh(sequencer)

    if not persist_session:
        self.close_session()

    return sequencer


def get_sequencer(self: "DBHandler", sequencer_id: int) -> Optional[models.Sequencer]:
    if not (persist_session := self._session is not None):
        self.open_session()

    sequencer = self.session.get(models.Sequencer, sequencer_id)

    if not persist_session:
        self.close_session()

    return sequencer


def get_sequencers(
    self: "DBHandler", limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None
) -> tuple[list[models.Sequencer], int]:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Sequencer)

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
    if not (persist_session := self._session is not None):
        self.open_session()

    count = self.session.query(models.Sequencer).count()

    if not persist_session:
        self.close_session()

    return count


def update_sequencer(self: "DBHandler", sequencer: models.Sequencer) -> models.Sequencer:
    if not (persist_session := self._session is not None):
        self.open_session()
    
    self.session.add(sequencer)
    self.session.commit()
    self.session.refresh(sequencer)

    if not persist_session:
        self.close_session()

    return sequencer


def get_sequencer_by_name(
    self: "DBHandler", name: str
) -> Optional[models.Sequencer]:
    if not (persist_session := self._session is not None):
        self.open_session()

    sequencer = self.session.query(models.Sequencer).where(
        models.Sequencer.name == name
    ).first()

    if not persist_session:
        self.close_session()

    return sequencer


def delete_sequencer(
    self: "DBHandler", sequencer_id: int,
    commit: bool = True
):
    if not (persist_session := self._session is not None):
        self.open_session()

    sequencer = self.session.get(models.Sequencer, sequencer_id)
    if not sequencer:
        raise exceptions.ElementDoesNotExist(f"Sequencer with id {sequencer_id} does not exist")
    
    if self.session.query(models.Experiment).where(
        models.Experiment.sequencer_id == sequencer_id
    ).first() is not None:
        raise exceptions.ElementIsReferenced(f"Sequencer with id {sequencer_id} is referenced by an experiment.")
    
    self.session.delete(sequencer)
    if commit:
        self.session.commit()

    if not persist_session:
        self.close_session()
    

def query_sequencers(
    self: "DBHandler", word: str, limit: Optional[int] = PAGE_LIMIT
) -> list[models.Sequencer]:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Sequencer).order_by(
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


    