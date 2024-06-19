import math
import string
from typing import Optional

import sqlalchemy as sa

from ...categories import PoolStatus, PoolStatusEnum, PoolTypeEnum
from ... import PAGE_LIMIT, models
from .. import exceptions


def create_pool(
    self, name: str,
    owner_id: int,
    contact_name: str,
    contact_email: str,
    pool_type: PoolTypeEnum,
    seq_request_id: Optional[int] = None,
    num_m_reads_requested: Optional[float] = None,
    status: PoolStatusEnum = PoolStatus.DRAFT,
    contact_phone: Optional[str] = None
) -> models.Pool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (user := self._session.get(models.User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    if seq_request_id is not None:
        if self._session.get(models.SeqRequest, seq_request_id) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

    pool = models.Pool(
        name=name.strip(),
        owner_id=owner_id,
        type_id=pool_type.id,
        seq_request_id=seq_request_id,
        num_m_reads_requested=num_m_reads_requested,
        contact=models.Contact(
            name=contact_name.strip(),
            email=contact_email.strip(),
            phone=contact_phone.strip() if contact_phone else None
        ),
        status_id=status.id,
        timestamp_stored_utc=sa.func.now() if status == PoolStatus.STORED else None
    )
    user.num_pools += 1

    self._session.add(pool)
    self._session.commit()
    self._session.refresh(pool)

    if not persist_session:
        self.close_session()

    return pool


def get_pool(self, pool_id: int) -> Optional[models.Pool]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    pool = self._session.get(models.Pool, pool_id)
    
    if not persist_session:
        self.close_session()

    return pool


def get_pools(
    self,
    user_id: Optional[int] = None,
    library_id: Optional[int] = None,
    experiment_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    status: Optional[PoolStatusEnum] = None,
    status_in: Optional[list[PoolStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.Pool], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Pool)
    if user_id is not None:
        query = query.where(
            models.Pool.owner_id == user_id
        )

    if library_id is not None:
        query = query.join(
            models.Library,
            models.Library.pool_id == models.Pool.id,
        ).where(
            models.Library.id == library_id
        )

    if experiment_id is not None:
        query = query.join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.Pool.id,
        ).where(
            models.ExperimentPoolLink.experiment_id == experiment_id
        )

    if seq_request_id is not None:
        query = query.where(
            models.Pool.seq_request_id == seq_request_id
        )

    if status is not None:
        query = query.where(
            models.Pool.status_id == status.id
        )

    if status_in is not None:
        query = query.where(
            models.Pool.status_id.in_([s.id for s in status_in])
        )

    if sort_by is not None:
        attr = getattr(models.Pool, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1
    
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    pools = query.all()

    if not persist_session:
        self.close_session()

    return pools, n_pages


def delete_pool(self, pool_id: int):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    pool.owner.num_pools -= 1

    self._session.delete(pool)
    self._session.commit()

    if not persist_session:
        self.close_session()


def update_pool(self, pool: models.Pool,) -> models.Pool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    self._session.add(pool)
    self._session.commit()
    self._session.refresh(pool)

    if not persist_session:
        self.close_session()
        
    return pool


def dilute_pool(
    self, pool_id: int, qubit_concentration: float,
    operator_id: int,
    volume_ul: Optional[float] = None,
    experiment_id: Optional[int] = None
) -> models.Pool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    if experiment_id is not None:
        if self._session.get(models.Experiment, experiment_id) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
        
    n = len(pool.dilutions)

    def to_identifier(n: int) -> str:
        out = ""

        while n >= 0:
            n, r = divmod(n, 26)
            out = string.ascii_uppercase[r] + out
            n -= 1

        return out

    dilution = models.PoolDilution(
        pool_id=pool_id,
        operator_id=operator_id,
        identifier=to_identifier(n),
        qubit_concentration=qubit_concentration,
        volume_ul=volume_ul,
        experiment_id=experiment_id,
    )

    pool.diluted_qubit_concentration = qubit_concentration
    pool.dilutions.append(dilution)

    self._session.add(dilution)
    self._session.commit()
    self._session.refresh(pool)

    if not persist_session:
        self.close_session()

    return pool


def query_pools(
    self, name: str, experiment_id: Optional[int] = None,
    status_in: Optional[list[PoolStatusEnum]] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.Pool]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Pool)

    if experiment_id is not None:
        query = query.join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.Pool.id,
        ).where(
            models.ExperimentPoolLink.experiment_id == experiment_id
        )

    if status_in is not None:
        query = query.where(
            models.Pool.status_id.in_([s.id for s in status_in])
        )

    query = query.order_by(
        sa.func.similarity(models.Pool.name, name).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    pools = query.all()

    if not persist_session:
        self.close_session()

    return pools


def get_pool_dilution(
    self, pool_id: int, identifier: str,
) -> Optional[models.PoolDilution]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    dilution = self._session.query(models.PoolDilution).where(
        models.PoolDilution.pool_id == pool_id,
        models.PoolDilution.identifier == identifier
    ).first()

    if not persist_session:
        self.close_session()

    return dilution


def get_pool_dilutions(
    self, pool_id: Optional[int] = None,
    experiment_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[models.PoolDilution], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if pool_id is not None and experiment_id is not None:
        raise Exception("Cannot filter by both pool_id and experiment_id")

    query = self._session.query(models.PoolDilution)
    if pool_id is not None:
        query = query.where(
            models.PoolDilution.pool_id == pool_id
        )

    if experiment_id is not None:
        query = query.join(
            models.Pool,
            models.Pool.id == models.PoolDilution.pool_id
        ).join(
            models.ExperimentPoolLink,
            models.ExperimentPoolLink.pool_id == models.Pool.id
        ).where(
            models.ExperimentPoolLink.experiment_id == experiment_id
        )

    if sort_by is not None:
        attr = getattr(models.PoolDilution, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1
    
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    dilutions = query.all()

    if not persist_session:
        self.close_session()

    return dilutions, n_pages


def get_next_pool_identifier(self, pool_type: PoolTypeEnum) -> str:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if not pool_type.identifier:
        raise TypeError(f"Pool type {pool_type} does not have an identifier")

    n_pools = self._session.query(models.Pool).where(
        models.Pool.type_id == pool_type.id
    ).count()

    identifier = f"{pool_type.identifier}{n_pools + 1:04d}"

    if not persist_session:
        self.close_session()

    return identifier