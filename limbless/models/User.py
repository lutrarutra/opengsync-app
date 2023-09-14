from typing import Optional, List, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

from .Links import ProjectUserLink, LibraryUserLink
from .. import serializer
from ..categories import UserRole

if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .Project import Project
    from .Library import Library


class UserMixin:
    """
    This provides default implementations for the methods that Flask-Login
    expects user objects to have.
    """

    # Python 3 implicitly set __hash__ to None if we override __eq__
    # We set it back to its default implementation
    __hash__ = object.__hash__
    __config__ = None

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return self.is_active

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        try:
            return str(self.id)
        except AttributeError:
            raise NotImplementedError("No `id` attribute - override `get_id`") from None

    def __eq__(self, other):
        """
        Checks the equality of two `UserMixin` objects using `get_id`.
        """
        if isinstance(other, UserMixin):
            return self.get_id() == other.get_id()
        return NotImplemented

    def __ne__(self, other):
        """
        Checks the inequality of two `UserMixin` objects using `get_id`.
        """
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented
        return not equal


class User(UserMixin, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str = Field(nullable=False, max_length=64)
    last_name: str = Field(nullable=False, max_length=64)
    email: str = Field(nullable=False, unique=True, index=True, max_length=128)
    password: str = Field(nullable=False, max_length=128)
    role: int = Field(nullable=False)

    requests: List["SeqRequest"] = Relationship(
        back_populates="requestor", sa_relationship_kwargs={"lazy": "joined"}
    )

    projects: List["Project"] = Relationship(
        back_populates="users", link_model=ProjectUserLink
    )
    libraries: List["Library"] = Relationship(
        back_populates="users", link_model=LibraryUserLink
    )

    @staticmethod
    def generate_registration_token(email: str):
        return serializer.dumps({"email": email})

    @staticmethod
    def verify_registration_token(token: str):
        try:
            email = serializer.loads(token, max_age=3600)["email"]
        except:  # FIXME: Specify exception
            return None
        return email

    @property
    def role_type(self) -> UserRole:
        return UserRole.as_dict()[self.role]
