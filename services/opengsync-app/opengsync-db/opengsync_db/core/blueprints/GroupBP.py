import math
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Query

from ... import models
from .. import exceptions
from ..DBBlueprint import DBBlueprint
from ... import PAGE_LIMIT
from ...categories import AffiliationType, AffiliationTypeEnum, GroupTypeEnum


class GroupBP(DBBlueprint):
    @classmethod
    def where(
        cls, query: Query, user_id: Optional[int], type: Optional[GroupTypeEnum] = None,
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

    @DBBlueprint.transaction
    def create(
        self, name: str, user_id: int, type: GroupTypeEnum, flush: bool = True
    ) -> models.Group:

        if self.db.session.query(models.Group).where(
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

        self.db.session.add(group)

        if flush:
            self.db.flush()
        return group

    @DBBlueprint.transaction
    def get(self, group_id: int) -> models.Group | None:
        res = self.db.session.get(models.Group, group_id)
        return res

    @DBBlueprint.transaction
    def get_with_name(self, name: str) -> models.Group | None:
        res = self.db.session.query(models.Group).where(
            models.Group.name == name
        ).first()
        return res

    @DBBlueprint.transaction
    def find(
        self,
        user_id: Optional[int], type: Optional[GroupTypeEnum] = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        type_in: Optional[list[GroupTypeEnum]] = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.Group], int | None]:
        query = self.db.session.query(models.Group)
        query = GroupBP.where(query, user_id=user_id, type=type, type_in=type_in)

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
        return res, n_pages

    @DBBlueprint.transaction
    def query(
        self, name: str, user_id: int | None = None, type: Optional[GroupTypeEnum] = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        type_in: Optional[list[GroupTypeEnum]] = None,
    ) -> list[models.Group]:
        query = self.db.session.query(models.Group)
        query = GroupBP.where(query, user_id=user_id, type=type, type_in=type_in)

        query = query.order_by(
            sa.func.similarity(models.Group.name, name).desc()
        )

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        groups = query.all()
        return groups

    @DBBlueprint.transaction
    def get_user_affiliation(self, user_id: int, group_id: int) -> models.links.UserAffiliation | None:
        res = self.db.session.query(models.links.UserAffiliation).where(
            models.links.UserAffiliation.user_id == user_id,
            models.links.UserAffiliation.group_id == group_id
        ).first()
        return res

    @DBBlueprint.transaction
    def get_affiliations(
        self, group_id: int, type: Optional[GroupTypeEnum] = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        type_in: Optional[list[GroupTypeEnum]] = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False
    ) -> tuple[list[models.links.UserAffiliation], int | None]:
        query = self.db.session.query(models.links.UserAffiliation).where(
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
        return affiliations, n_pages

    @DBBlueprint.transaction
    def update(self, group: models.Group):
        self.db.session.add(group)

    @DBBlueprint.transaction
    def add_user(self, user_id: int, group_id: int, affiliation_type: AffiliationTypeEnum) -> models.Group:

        if (group := self.db.session.get(models.Group, group_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
        
        if self.db.session.query(models.links.UserAffiliation).where(
            models.links.UserAffiliation.user_id == user_id,
            models.links.UserAffiliation.group_id == group_id
        ).first() is not None:
            raise exceptions.NotUniqueValue(f"User {user_id} is already in group {group_id}")

        group.user_links.append(models.links.UserAffiliation(
            user_id=user_id,
            group_id=group_id,
            affiliation_type_id=affiliation_type.id
        ))

        self.db.session.add(group)
        return group
    
    @DBBlueprint.transaction
    def change_user_affiliation(self, user_id: int, group_id: int, new_affiliation_type: AffiliationTypeEnum) -> models.Group:
        if (group := self.db.session.get(models.Group, group_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
        
        if (affiliation := self.db.session.query(models.links.UserAffiliation).where(
            models.links.UserAffiliation.user_id == user_id,
            models.links.UserAffiliation.group_id == group_id
        ).first()) is None:
            raise exceptions.ElementDoesNotExist(f"User {user_id} is not in group {group_id}")

        affiliation.affiliation_type = new_affiliation_type
        self.db.session.add(affiliation)
        self.db.session.add(group)
        return group

    @DBBlueprint.transaction
    def remove_user(self, user_id: int, group_id: int) -> models.Group:
        if (group := self.db.session.get(models.Group, group_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Group with id {group_id} not found")
        
        if (affiliation := self.db.session.query(models.links.UserAffiliation).where(
            models.links.UserAffiliation.user_id == user_id,
            models.links.UserAffiliation.group_id == group_id
        ).first()) is None:
            raise exceptions.ElementDoesNotExist(f"User {user_id} is not in group {group_id}")

        group.user_links.remove(affiliation)
        self.db.session.delete(affiliation)

        self.db.session.add(group)
        return group
    
    @DBBlueprint.transaction
    def __getitem__(self, group_id: int) -> models.Group:
        if (group := self.db.session.get(models.Group, group_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Group with id {group_id} does not exist")
        return group