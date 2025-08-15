import math
from typing import Optional

import sqlalchemy as sa

from opengsync_db import models


from .. import exceptions
from ..DBBlueprint import DBBlueprint
from ... import PAGE_LIMIT
from ...categories import UserRole, UserRoleEnum, AffiliationTypeEnum


class UserBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, email: str,
        first_name: str,
        last_name: str,
        hashed_password: str,
        role: UserRoleEnum,
        flush: bool = True
    ) -> models.User:
        if self.db.session.query(models.User).where(
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
        self.db.session.add(user)
        
        if flush:
            self.db.flush()
        return user

    @DBBlueprint.transaction
    def get(self, user_id: int) -> models.User | None:
        res = self.db.session.get(models.User, user_id)
        return res

    @DBBlueprint.transaction
    def get_with_email(self, email: str) -> models.User | None:
        user = self.db.session.query(models.User).where(
            models.User.email == email
        ).first()
        return user

    @DBBlueprint.transaction
    def find(
        self, limit: int | None = PAGE_LIMIT, offset: int | None = None,
        role_in: Optional[list[UserRoleEnum]] = None,
        sort_by: Optional[str] = None, descending: bool = False,
        group_id: int | None = None, exclude_group_id: int | None = None,
        count_pages: bool = False
    ) -> tuple[list[models.User], int | None]:
        query = self.db.session.query(models.User)

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

        return users, n_pages

    @DBBlueprint.transaction
    def update(self, user: models.User) -> models.User:
        self.db.session.add(user)
        return user

    @DBBlueprint.transaction
    def delete(self, user_id: int, flush: bool = True) -> None:
        if (user := self.db.session.get(models.User, user_id)) is None:
            raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

        self.db.session.delete(user)
        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def query(
        self, word: str, role_in: Optional[list[UserRoleEnum]] = None,
        only_insiders: bool = False, limit: int | None = PAGE_LIMIT
    ) -> list[models.User]:
        query = self.db.session.query(models.User)

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
        return users

    @DBBlueprint.transaction
    def query_with_email(
        self, word: str, role_in: Optional[list[UserRoleEnum]] = None, limit: int | None = PAGE_LIMIT
    ) -> list[models.User]:
        query = self.db.session.query(models.User)

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
        return users

    @DBBlueprint.transaction
    def get_affiliations(
        self, user_id: int, limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False, affiliation_type: Optional[AffiliationTypeEnum] = None,
        count_pages: bool = False
    ) -> tuple[list[models.links.UserAffiliation], int | None]:
        query = self.db.session.query(models.links.UserAffiliation).where(
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
        return res, n_pages

    @DBBlueprint.transaction
    def __getitem__(self, key: int | str) -> models.User:
        if isinstance(key, int):
            if (user := self.get(key)) is None:
                raise exceptions.ElementDoesNotExist(f"User with id {key} does not exist")
            return user
        elif isinstance(key, str):
            if (user := self.get_with_email(key)) is None:
                raise exceptions.ElementDoesNotExist(f"User with email {key} does not exist")
            return user
        else:
            raise TypeError(f"Key must be int or str, got {type(key).__name__}")