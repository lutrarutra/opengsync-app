import math
from typing import Optional

from sqlmodel import func

from ... import bcrypt, PAGE_LIMIT
from ...models import User
from .. import exceptions
from ...categories import UserRole


def create_user(
    self, email: str,
    first_name: str,
    last_name: str,
    password: str,
    role: UserRole,
    commit: bool = True
) -> User:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(User).where(
        User.email == email
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"User with email {email} already exists")

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=hashed_password,
        role=role.value.id,
    )

    self._session.add(user)
    if commit:
        self._session.commit()
        self._session.refresh(user)

    if not persist_session:
        self.close_session()
    return user


def get_user(self, user_id: int) -> User:
    
    persist_session = self._session is not None
    if self._session is None:
        self.open_session()

    res = self._session.get(User, user_id)

    if not persist_session:
        self.close_session()
        
    return res


def get_user_by_email(self, email: str) -> User:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    user = self._session.query(User).where(
        User.email == email
    ).first()
    if not persist_session:
        self.close_session()
    return user


def get_users(
    self, limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False
) -> tuple[list[User], int]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(User)

    if sort_by is not None:
        attr = getattr(User, sort_by)
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
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(User).count()
    
    if not persist_session:
        self.close_session()
    return res


def update_user(
    self, user_id: int,
    email: Optional[str] = None,
    password: Optional[str] = None,
    role: Optional[UserRole] = None,
    commit: bool = True
) -> User:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (user := self._session.get(User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

    if email is not None:
        user.email = email
    if password is not None:
        user.password = bcrypt.generate_password_hash(password).decode("utf-8")
    if role is not None:
        if not UserRole.is_valid(role):
            raise exceptions.InvalidRole(f"Invalid role {role}")
        user.role = role

    if commit:
        self._session.commit()
        self._session.refresh(user)

    if not persist_session:
        self.close_session()
    return user


def delete_user(self, user_id: int, commit: bool = True) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    user = self._session.get(User, user_id)
    if not user:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

    self._session.delete(user)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def query_users(
    self, word: str, with_roles: Optional[list[UserRole]] = None,
    only_insiders: bool = False, limit: Optional[int] = PAGE_LIMIT
) -> list[User]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(User)

    query = query.order_by(
        func.similarity(User.first_name + ' ' + User.last_name, word).desc()
    )

    if only_insiders:
        query = query.where(
            User.role != UserRole.CLIENT.value.id
        )

    if with_roles is not None:
        status_ids = [role.value.id for role in with_roles]
        query = query.where(
            User.role.in_(status_ids)
        )

    if limit is not None:
        query = query.limit(limit)

    users = query.all()

    if not persist_session:
        self.close_session()

    return users


def query_users_by_email(self, word: str, limit: Optional[int] = PAGE_LIMIT) -> list[User]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(User)

    query = query.order_by(
        func.similarity(User.email, word).desc(),
    )

    if limit is not None:
        query = query.limit(limit)

    users = query.all()

    if not persist_session:
        self.close_session()

    return users
