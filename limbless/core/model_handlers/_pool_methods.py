import math
from typing import Optional

from sqlmodel import func

from ... import PAGE_LIMIT
from ...models import Pool, User, Library
from .. import exceptions


def create_pool(
    self, name: str,
    owner_id: int,
    contact_name: str,
    contact_email: str,
    contact_phone: Optional[str] = None,
    commit: bool = True
) -> Pool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (user := self._session.get(User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    pool = Pool(
        name=name,
        owner_id=owner_id,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
    )
    self._session.add(pool)
    user.num_pools += 1

    if commit:
        self._session.commit()
        self._session.refresh(pool)

    if not persist_session:
        self.close_session()

    return pool


def get_pool(self, pool_id: int) -> Pool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    pool = self._session.get(Pool, pool_id)
    if not persist_session:
        self.close_session()
    return pool


def get_pools(
    self,
    user_id: Optional[int] = None,
    library_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
) -> tuple[list[Pool], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(Pool)
    if user_id is not None:
        query = query.where(
            Pool.owner_id == user_id
        )

    if library_id is not None:
        query = query.join(
            Library,
            Library.pool_id == Pool.id,
            isouter=True
        ).where(
            Library.id == library_id
        )

    if sort_by is not None:
        attr = getattr(Pool, sort_by)
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

    if (pool := self._session.get(Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    pool.owner.num_pools -= 1
    for sample in pool.samples:
        sample.num_pools -= 1
        
    self._session.delete(pool)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def update_pool(
    self, pool_id: int,
    name: Optional[str] = None,
    commit: bool = True
) -> Pool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    pool = self._session.get(Pool, pool_id)
    if not pool:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    if name is not None:
        _lib = self._session.query(Pool).where(
            Pool.name == name
        ).first()
        if _lib is not None and _lib.id != pool_id:
            raise exceptions.NotUniqueValue(f"Pool with name {name} already exists")

    if name is not None:
        pool.name = name

    if commit:
        self._session.commit()
        self._session.refresh(pool)

    if not persist_session:
        self.close_session()
    return pool


def query_pools(
    self, word: str,
    user_id: Optional[int] = None,
    library_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
) -> list[Pool]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(Pool)

    if user_id is not None:
        if self._session.get(User, user_id) is None:
            raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
        query = query.where(
            Pool.owner_id == user_id
        )

    if library_id is not None:
        query = query.join(
            Library,
            SamplePoolLink.pool_id == Pool.id,
            isouter=True
        ).where(
            SamplePoolLink.sample_id == sample_id
        )

    query = query.order_by(
        func.similarity(Pool.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    pools = query.all()

    if not persist_session:
        self.close_session()

    return pools