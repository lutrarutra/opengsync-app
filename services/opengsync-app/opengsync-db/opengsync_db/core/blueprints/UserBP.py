import math
from typing import Optional, Callable

import sqlalchemy as sa
from sqlalchemy.orm import Query
from sqlalchemy.sql.base import ExecutableOption

from opengsync_db import models


from .. import exceptions
from ..DBBlueprint import DBBlueprint
from ... import PAGE_LIMIT
from ...categories import UserRole, UserRoleEnum, AffiliationTypeEnum


class UserBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        role_in: Optional[list[UserRoleEnum]] = None,
        group_id: int | None = None,
        exclude_group_id: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
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

        if custom_query is not None:
            query = custom_query(query)

        return query
    
    @DBBlueprint.transaction
    def create(
        self, email: str,
        first_name: str,
        last_name: str,
        hashed_password: str,
        role: UserRoleEnum,
        flush: bool = True
    ) -> models.User:
        """Create a new user.

        Args:
            email (str): valid email address
            first_name (str): first name
            last_name (str): last name
            hashed_password (str): hashed password
            role (UserRoleEnum): UserRoleEnum
            flush (bool, optional): flushes object to session. Defaults to True.

        Raises:
            exceptions.NotUniqueValue: when email is already in use

        Returns:
            models.User: user object
        """
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
    def get(self, user_id: int, options: ExecutableOption | None = None) -> models.User | None:
        """get user by id

        Args:
            user_id (int): user id
            options (ExecutableOption | None, optional): sqlalchemy loading options. Defaults to None.

        Returns:
            models.User | None: _user object or None if not found_
        """
        if options is not None:
            res = self.db.session.query(models.User).options(options).filter(models.User.id == user_id).first()
        else:
            res = self.db.session.get(models.User, user_id)
        return res

    @DBBlueprint.transaction
    def get_with_email(self, email: str) -> models.User | None:
        """get user by email

        Args:
            email (str): email address

        Returns:
            models.User | None: user object or None if not found
        """
        user = self.db.session.query(models.User).where(
            models.User.email == email
        ).first()
        return user

    @DBBlueprint.transaction
    def find(
        self,
        role_in: Optional[list[UserRoleEnum]] = None,
        group_id: int | None = None, exclude_group_id: int | None = None,
        name: str | None = None,
        id: int | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        page: int | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.User], int | None]:
        """Query users

        Args:
            role_in (Optional[list[UserRoleEnum]], optional): filter users by role. Defaults to None.
            group_id (int | None, optional): filter users by group. Defaults to None.
            exclude_group_id (int | None, optional): exclude users from group. Defaults to None.
            offset (int | None, optional): offset for paging. Defaults to None.
            limit (int | None, optional): maximum number of elements returned. Defaults to PAGE_LIMIT.
            sort_by (Optional[str], optional): sort users by. Defaults to None.
            descending (bool, optional): larger first. Defaults to False.
            count_pages (bool, optional): count how many pages there are. Defaults to False.

        Returns:
            tuple[list[models.User], int | None]: list of users, number of pages or None if count_pages is False
        """
        query = self.db.session.query(models.User)
        query = self.where(
            query, role_in=role_in, group_id=group_id,
            exclude_group_id=exclude_group_id
        )
        if options is not None:
            query = query.options(options)
            
        if sort_by is not None:
            attr = getattr(models.User, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)
        
        if name is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity((models.User.first_name + ' ' + models.User.last_name), name).desc()))
        elif id is not None:
            query = query.where(models.User.id == id)

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        users = query.all()

        return users, n_pages

    @DBBlueprint.transaction
    def update(self, user: models.User):
        """update user

        Args:
            user (models.User): user with updates
        """
        self.db.session.add(user)

    @DBBlueprint.transaction
    def delete(self, user_id: int, flush: bool = True) -> None:
        """_summary_

        Args:
            user_id (int): id of user to delete
            flush (bool, optional): removes user from session. Defaults to True.

        Raises:
            exceptions.ElementDoesNotExist: if user with user_id does not exist
        """
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
        """Natural language search for users by first name and last name.

        Args:
            word (str): search word
            role_in (Optional[list[UserRoleEnum]], optional): filter users by id. Defaults to None.
            only_insiders (bool, optional): _description_. Defaults to False.
            limit (int | None, optional): _description_. Defaults to PAGE_LIMIT.

        Returns:
            list[models.User]: _description_
        """
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
        group_name: str | None = None,
        page: int | None = None
    ) -> tuple[list[models.links.UserAffiliation], int | None]:
        query = self.db.session.query(models.links.UserAffiliation).where(
            models.links.UserAffiliation.user_id == user_id
        )

        if affiliation_type is not None:
            query = query.where(
                models.links.UserAffiliation.affiliation_type_id == affiliation_type.id
            )

        if sort_by is not None:
            attr = getattr(models.links.UserAffiliation, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        if group_name is not None:
            query = query.join(
                models.Group,
                models.Group.id == models.links.UserAffiliation.group_id
            ).order_by(
                sa.nulls_last(sa.func.similarity(models.Group.name, group_name).desc())
            )

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

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