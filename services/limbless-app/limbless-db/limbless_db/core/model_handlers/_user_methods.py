import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

from limbless_db import models

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from .. import exceptions
from ... import PAGE_LIMIT
from ...categories import UserRole, UserRoleEnum, AffiliationTypeEnum


def create_user(
    self: "DBHandler", email: str,
    first_name: str,
    last_name: str,
    hashed_password: str,
    role: UserRoleEnum,
    commit: bool = True
) -> models.User:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.query(models.User).where(
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

    self.session.add(user)
    if commit:
        self.session.commit()
        self.session.refresh(user)

    if not persist_session:
        self.close_session()
    return user


def get_user(self: "DBHandler", user_id: int) -> models.User | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.User, user_id)

    if not persist_session:
        self.close_session()
        
    return res


def get_user_by_email(self: "DBHandler", email: str) -> models.User | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    user = self.session.query(models.User).where(
        models.User.email == email
    ).first()

    if not persist_session:
        self.close_session()
    return user


def get_users(
    self: "DBHandler", limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    role_in: Optional[list[UserRoleEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    group_id: Optional[int] = None, exclude_group_id: Optional[int] = None,
    count_pages: bool = False
) -> tuple[list[models.User], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.User)

    if role_in is not None:
        role_ids = [role.id for role in role_in]
        query = query.where(
            models.User.role_id.in_(role_ids)
        )

    if group_id is not None:
        query = query.join(
            models.links.UserAffiliation,
            models.links.UserAffiliation.user_id == models.User.id
        ).where(
            models.links.UserAffiliation.group_id == group_id
        )

    if exclude_group_id is not None:
        query = query.join(
            models.links.UserAffiliation,
            models.links.UserAffiliation.user_id == models.User.id
        ).where(
            models.links.UserAffiliation.group_id != exclude_group_id
        )
        
    if sort_by is not None:
        attr = getattr(models.User, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    users = query.all()

    if not persist_session:
        self.close_session()
    return users, n_pages


def get_num_users(self: "DBHandler") -> int:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.query(models.User).count()
    
    if not persist_session:
        self.close_session()
    return res


def update_user(
    self: "DBHandler", user: models.User
) -> models.User:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(user)
    self.session.commit()
    self.session.refresh(user)

    if not persist_session:
        self.close_session()
    return user


def delete_user(self: "DBHandler", user_id: int) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (user := self.session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

    self.session.delete(user)
    self.session.commit()

    if not persist_session:
        self.close_session()


def query_users(
    self: "DBHandler", word: str, role_in: Optional[list[UserRoleEnum]] = None,
    only_insiders: bool = False, limit: Optional[int] = PAGE_LIMIT
) -> list[models.User]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.User)

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
    self: "DBHandler", word: str, role_in: Optional[list[UserRoleEnum]] = None, limit: Optional[int] = PAGE_LIMIT
) -> list[models.User]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.User)

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
    self: "DBHandler", user_id: int, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False, affiliation_type: Optional[AffiliationTypeEnum] = None,
    count_pages: bool = False
) -> tuple[list[models.links.UserAffiliation], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.links.UserAffiliation).where(
        models.links.UserAffiliation.user_id == user_id
    )

    if affiliation_type is not None:
        query = query.where(
            models.links.UserAffiliation.affiliation_type_id == affiliation_type.id
        )

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    if sort_by is not None:
        attr = getattr(models.links.UserAffiliation, sort_by)
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