import math
from typing import Optional

import sqlalchemy as sa

from limbless_db import models

from .. import exceptions
from ... import PAGE_LIMIT
from ...categories import UserRole, UserRoleEnum, AffiliationTypeEnum


def create_user(
    self, email: str,
    first_name: str,
    last_name: str,
    hashed_password: str,
    role: UserRoleEnum,
    commit: bool = True
) -> models.User:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self._session.query(models.User).where(
        models.User.email == email
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"User with email {email} already exists")

    user = models.User(
        email=email.strip(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        password=hashed_password,
        role_id=role.id,
    )

    self._session.add(user)
    if commit:
        self._session.commit()
        self._session.refresh(user)

    if not persist_session:
        self.close_session()
    return user


def get_user(self, user_id: int) -> Optional[models.User]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self._session.get(models.User, user_id)

    if not persist_session:
        self.close_session()
        
    return res


def get_user_by_email(self, email: str) -> models.User:
    if not (persist_session := self._session is not None):
        self.open_session()

    user = self._session.query(models.User).where(
        models.User.email == email
    ).first()
    if not persist_session:
        self.close_session()
    return user


def get_users(
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    role_in: Optional[list[UserRoleEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    group_id: Optional[int] = None
) -> tuple[list[models.User], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.User)

    if role_in is not None:
        role_ids = [role.id for role in role_in]
        query = query.where(
            models.User.role_id.in_(role_ids)
        )

    if group_id is not None:
        query = query.join(
            models.UserAffiliation,
            models.UserAffiliation.user_id == models.User.id
        ).where(
            models.UserAffiliation.group_id == group_id
        )
        
    if sort_by is not None:
        attr = getattr(models.User, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    users = query.all()

    if not persist_session:
        self.close_session()
    return users, n_pages


def get_num_users(self) -> int:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self._session.query(models.User).count()
    
    if not persist_session:
        self.close_session()
    return res


def update_user(
    self, user: models.User
) -> models.User:
    if not (persist_session := self._session is not None):
        self.open_session()

    self._session.add(user)
    self._session.commit()
    self._session.refresh(user)

    if not persist_session:
        self.close_session()
    return user


def delete_user(self, user_id: int) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (user := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

    self._session.delete(user)
    self._session.commit()

    if not persist_session:
        self.close_session()


def query_users(
    self, word: str, role_in: Optional[list[UserRoleEnum]] = None,
    only_insiders: bool = False, limit: Optional[int] = PAGE_LIMIT
) -> list[models.User]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.User)

    if only_insiders:
        query = query.where(
            models.User.role_id != UserRole.CLIENT.id
        )

    if role_in is not None:
        query = query.where(
            models.User.role_id.in_([role.id for role in role_in])
        )

    query = query.order_by(
        sa.func.similarity(models.User.first_name + ' ' + models.User.last_name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    users = query.all()

    if not persist_session:
        self.close_session()

    return users


def query_users_by_email(
    self, word: str, role_in: Optional[list[UserRoleEnum]] = None, limit: Optional[int] = PAGE_LIMIT
) -> list[models.User]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.User)

    if role_in is not None:
        query = query.where(
            models.User.role_id.in_([role.id for role in role_in])
        )

    query = query.order_by(
        sa.func.similarity(models.User.email, word).desc(),
    )

    if limit is not None:
        query = query.limit(limit)

    users = query.all()

    if not persist_session:
        self.close_session()

    return users


def get_user_affiliations(
    self, user_id: int, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False, affiliation_type: Optional[AffiliationTypeEnum] = None
) -> tuple[list[models.UserAffiliation], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.UserAffiliation).where(
        models.UserAffiliation.user_id == user_id
    )

    if affiliation_type is not None:
        query = query.where(
            models.UserAffiliation.affiliation_type_id == affiliation_type.id
        )

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        attr = getattr(models.UserAffiliation, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages