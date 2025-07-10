import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Query

from limbless_db import models

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from .. import exceptions
from ... import PAGE_LIMIT
from ...categories import AffiliationType, AffiliationTypeEnum, GroupTypeEnum


def create_group(
    self: "DBHandler", name: str, user_id: int, type: GroupTypeEnum
) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self.session.query(models.Group).where(
        models.Group.name == name
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"Group with name {name} already exists")
    
    group = models.Group(
        name=name.strip(),
        type_id=type.id
    )
    group.user_links = [models.links.UserAffiliation(
        user_id=user_id,
        affiliation_type_id=AffiliationType.OWNER.id
    )]

    self.session.add(group)

    self.session.commit()
    self.session.refresh(group)

    if not persist_session:
        self.close_session()

    return group


def get_group(self: "DBHandler", group_id: int) -> models.Group | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Group, group_id)

    if not persist_session:
        self.close_session()
        
    return res


def get_group_by_name(self: "DBHandler", name: str) -> models.Group | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.query(models.Group).where(
        models.Group.name == name
    ).first()

    if not persist_session:
        self.close_session()

    return res


def where(
    query: Query, user_id: Optional[int], type: Optional[GroupTypeEnum] = None,
    type_in: Optional[list[GroupTypeEnum]] = None
) -> Query:
    if type is not None:
        query = query.where(models.Group.type_id == type.id)
    if user_id is not None:
        query = query.join(
            models.links.UserAffiliation,
            models.links.UserAffiliation.group_id == models.Group.id
        ).where(
            models.links.UserAffiliation.user_id == user_id
        )
    if type_in is not None:
        query = query.where(models.Group.type_id.in_([t.id for t in type_in]))

    return query


def get_groups(
    self: "DBHandler",
    user_id: Optional[int], type: Optional[GroupTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    type_in: Optional[list[GroupTypeEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.Group], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Group)
    query = where(query, user_id=user_id, type=type, type_in=type_in)

    n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

    if sort_by is not None:
        attr = getattr(models.Group, sort_by)
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


def query_groups(
    self: "DBHandler", name: str, user_id: Optional[int] = None, type: Optional[GroupTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    type_in: Optional[list[GroupTypeEnum]] = None,
) -> list[models.Group]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Group)
    query = where(query, user_id=user_id, type=type, type_in=type_in)

    query = query.order_by(
        sa.func.similarity(models.Group.name, name).desc()
    )

    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)

    groups = query.all()

    if not persist_session:
        self.close_session()

    return groups


def get_group_user_affiliation(self: "DBHandler", user_id: int, group_id: int) -> models.links.UserAffiliation | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.query(models.links.UserAffiliation).where(
        models.links.UserAffiliation.user_id == user_id,
        models.links.UserAffiliation.group_id == group_id
    ).first()

    if not persist_session:
        self.close_session()

    return res


def get_group_affiliations(
    self: "DBHandler", group_id: int, type: Optional[GroupTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    type_in: Optional[list[GroupTypeEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False
) -> tuple[list[models.links.UserAffiliation], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self.session.get(models.Group, group_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
    
    query = self.session.query(models.links.UserAffiliation).where(
        models.links.UserAffiliation.group_id == group_id
    )

    if type is not None:
        query = query.where(models.links.UserAffiliation.affiliation_type_id == type.id)

    if type_in is not None:
        query = query.where(models.links.UserAffiliation.affiliation_type_id.in_([t.id for t in type_in]))

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

    affiliations = query.all()

    if not persist_session:
        self.close_session()

    return affiliations, n_pages


def update_group(self: "DBHandler", group: models.Group) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(group)
    self.session.commit()
    self.session.refresh(group)

    if not persist_session:
        self.close_session()

    return group


def add_user_to_group(self: "DBHandler", user_id: int, group_id: int, affiliation_type: AffiliationTypeEnum) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self.session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} not found")
    
    if (group := self.session.get(models.Group, group_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
    
    if self.session.query(models.links.UserAffiliation).where(
        models.links.UserAffiliation.user_id == user_id,
        models.links.UserAffiliation.group_id == group_id
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"User {user_id} is already in group {group_id}")

    group.user_links.append(models.links.UserAffiliation(
        user_id=user_id,
        group_id=group_id,
        affiliation_type_id=affiliation_type.id
    ))

    self.session.add(group)
    self.session.commit()
    self.session.refresh(group)

    if not persist_session:
        self.close_session()

    return group


def remove_user_from_group(self: "DBHandler", user_id: int, group_id: int) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self.session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} not found")
    
    if (group := self.session.get(models.Group, group_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
    
    if (affiliation := self.session.query(models.links.UserAffiliation).where(
        models.links.UserAffiliation.user_id == user_id,
        models.links.UserAffiliation.group_id == group_id
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"User {user_id} is not in group {group_id}")

    group.user_links.remove(affiliation)
    self.session.delete(affiliation)

    self.session.add(group)
    self.session.commit()
    self.session.refresh(group)

    if not persist_session:
        self.close_session()

    return group