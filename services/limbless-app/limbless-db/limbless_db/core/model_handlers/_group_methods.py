import math
from typing import Optional

import sqlalchemy as sa

from limbless_db import models

from .. import exceptions
from ... import PAGE_LIMIT
from ...categories import AffiliationType, AffiliationTypeEnum, GroupTypeEnum


def create_group(
    self, name: str, user_id: int, type: GroupTypeEnum
) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    if self._session.query(models.Group).where(
        models.Group.name == name
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"Group with name {name} already exists")
    
    group = models.Group(
        name=name.strip(),
        type_id=type.id
    )
    group.user_links = [models.UserAffiliation(
        user_id=user_id,
        affiliation_type_id=AffiliationType.OWNER.id
    )]

    self._session.add(group)

    self._session.commit()
    self._session.refresh(group)

    if not persist_session:
        self.close_session()

    return group


def get_group(self, group_id: int) -> Optional[models.Group]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self._session.get(models.Group, group_id)

    if not persist_session:
        self.close_session()
        
    return res


def get_groups(
    self,
    user_id: Optional[int], type: Optional[GroupTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    type_in: Optional[list[GroupTypeEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False
) -> tuple[list[models.Group], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.Group)

    if type is not None:
        query = query.where(models.Group.type_id == type.id)
    if user_id is not None:
        query = query.join(
            models.UserAffiliation,
            models.UserAffiliation.group_id == models.Group.id
        ).where(
            models.UserAffiliation.user_id == user_id
        )
    elif type_in is not None:
        query = query.where(models.Group.type_id.in_([t.id for t in type_in]))

    n_pages = math.ceil(query.count() / limit) if limit is not None else 1

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


def get_group_user_affiliation(self, user_id: int, group_id: int) -> Optional[models.UserAffiliation]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self._session.query(models.UserAffiliation).where(
        models.UserAffiliation.user_id == user_id,
        models.UserAffiliation.group_id == group_id
    ).first()

    if not persist_session:
        self.close_session()

    return res


def get_group_affiliations(
    self, group_id: int, type: Optional[GroupTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    type_in: Optional[list[GroupTypeEnum]] = None,
    sort_by: Optional[str] = None, descending: bool = False
) -> tuple[list[models.UserAffiliation], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self._session.get(models.Group, group_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
    
    query = self._session.query(models.UserAffiliation).where(
        models.UserAffiliation.group_id == group_id
    )

    if type is not None:
        query = query.where(models.UserAffiliation.affiliation_type_id == type.id)

    if type_in is not None:
        query = query.where(models.UserAffiliation.affiliation_type_id.in_([t.id for t in type_in]))

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

    affiliations = query.all()

    if not persist_session:
        self.close_session()

    return affiliations, n_pages


def update_group(self, group: models.Group) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    self._session.add(group)
    self._session.commit()
    self._session.refresh(group)

    if not persist_session:
        self.close_session()

    return group


def add_user_to_group(self, user_id: int, group_id: int, affiliation_type: AffiliationTypeEnum) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} not found")
    
    if (group := self._session.get(models.Group, group_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
    
    if self._session.query(models.UserAffiliation).where(
        models.UserAffiliation.user_id == user_id,
        models.UserAffiliation.group_id == group_id
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"User {user_id} is already in group {group_id}")

    group.user_links.append(models.UserAffiliation(
        user_id=user_id,
        group_id=group_id,
        affiliation_type_id=affiliation_type.id
    ))

    self._session.add(group)
    self._session.commit()
    self._session.refresh(group)

    if not persist_session:
        self.close_session()

    return group


def remove_user_from_group(self, user_id: int, group_id: int) -> models.Group:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} not found")
    
    if (group := self._session.get(models.Group, group_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
    
    if (affiliation := self._session.query(models.UserAffiliation).where(
        models.UserAffiliation.user_id == user_id,
        models.UserAffiliation.group_id == group_id
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"User {user_id} is not in group {group_id}")

    group.user_links.remove(affiliation)
    self._session.delete(affiliation)

    self._session.add(group)
    self._session.commit()
    self._session.refresh(group)

    if not persist_session:
        self.close_session()

    return group


def query_groups(
    self, name: str, user_id: Optional[int] = None, type: Optional[GroupTypeEnum] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    type_in: Optional[list[GroupTypeEnum]] = None,
) -> list[models.Group]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.Group)

    if type is not None:
        query = query.where(models.Group.type_id == type.id)
    if user_id is not None:
        query = query.join(models.UserAffiliation).where(
            models.UserAffiliation.user_id == user_id
        )
    elif type_in is not None:
        query = query.where(models.Group.type_id.in_([t.id for t in type_in]))

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