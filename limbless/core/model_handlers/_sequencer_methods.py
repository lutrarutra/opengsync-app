from typing import Optional

from sqlmodel import func

from ... import models
from .. import exceptions
from ...tools import SearchResult


def create_sequencer(
    self, name: str,
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
    
    sequencer = models.Sequencer(name=name, ip=ip)

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
    self, limit: Optional[int] = None, offset: Optional[int] = None
) -> list[models.Sequencer]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sequencer)

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    sequencers = query.all()

    if not persist_session:
        self.close_session()

    return sequencers


def get_num_sequencers(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    count = self._session.query(models.Sequencer).count()

    if not persist_session:
        self.close_session()

    return count


def update_sequencer(
    self, sequencer_id: int, name: Optional[str] = None,
    ip: Optional[str] = None, commit: bool = True
) -> models.Sequencer:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (sequencer := self._session.get(models.Sequencer, sequencer_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sequencer with id '{sequencer_id}' does not exist.")
    
    if name is not None:
        sequencer.name = name

    if ip is not None:
        sequencer.ip = ip

    if commit:
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
    self, word: str, limit: Optional[int] = 20
) -> list[SearchResult]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sequencer).order_by(
        func.similarity(
            models.Sequencer.name, word
        ).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    res = [SearchResult(sequencer.id, sequencer.name, sequencer.ip) for sequencer in res]

    if not persist_session:
        self.close_session()

    return res


    