import math
from typing import Optional

import sqlalchemy as sa

from ...categories import PoolStatus, PoolStatusEnum
from ... import PAGE_LIMIT, models
from .. import exceptions


def create_pool(
    self, name: str,
    owner_id: int,
    seq_request_id: Optional[int],
    num_m_reads_requested: Optional[float],
    contact_name: str,
    contact_email: str,
    status: PoolStatusEnum = PoolStatus.DRAFT,
    contact_phone: Optional[str] = None,
    commit: bool = True
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
        name=name,
        owner_id=owner_id,
        seq_request_id=seq_request_id,
        num_m_reads_requested=num_m_reads_requested,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        status_id=status.id
    )
    self._session.add(pool)
    user.num_pools += 1

    if commit:
        self._session.commit()
        self._session.refresh(pool)

    if not persist_session:
        self.close_session()

    return pool


def get_pool(self, pool_id: int) -> models.Pool:
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
        query = query.where(
            models.Pool.experiment_id == experiment_id
        )

    if seq_request_id is not None:
        query = query.where(
            models.Pool.seq_request_id == seq_request_id
        )

    if status is not None:
        query = query.where(
            models.Pool.status_id == status.id
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


def delete_pool(
    self, pool_id: int,
    commit: bool = True
) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    pool.owner.num_pools -= 1
    for sample in pool.samples:
        sample.num_pools -= 1
        
    self._session.delete(pool)
    if commit:
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


def query_pools(
    self, name: str, experiment_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT
) -> list[models.Pool]:
    persist_session = self._session is not None
    raise NotImplementedError("This method is not implemented yet.")
    if not self._session:
        self.open_session()

    query = sa.select(models.Pool).order_by(
        sa.func.similarity(models.Pool.name, name).desc()
    )

    if experiment_id is not None:
        query = query.where(models.Pool.experiment_id == experiment_id)

    if limit is not None:
        query = query.limit(limit)

    pools = self._session.execute(query).scalars().all()

    if not persist_session:
        self.close_session()

    return pools