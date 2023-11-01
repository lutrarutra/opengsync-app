from typing import Optional, List, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship
from itsdangerous import SignatureExpired, BadSignature

from .. import serializer, models
from ..categories import UserRole

if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .Project import Project
    from .Library import Library
    from .Sample import Sample


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
    id: int = Field(default=None, primary_key=True)
    first_name: str = Field(nullable=False, max_length=64)
    last_name: str = Field(nullable=False, max_length=64)
    email: str = Field(nullable=False, unique=True, index=True, max_length=128)
    password: str = Field(nullable=False, max_length=128)
    role: int = Field(nullable=False)

    num_projects: int = Field(nullable=False, default=0)
    num_libraries: int = Field(nullable=False, default=0)
    num_samples: int = Field(nullable=False, default=0)
    num_seq_requests: int = Field(nullable=False, default=0)

    requests: List["SeqRequest"] = Relationship(
        back_populates="requestor",
        sa_relationship_kwargs={"lazy": "noload"}
    )
    projects: List["Project"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "noload"}
    )
    libraries: List["Library"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "noload"}
    )
    samples: List["Sample"] = Relationship(
        back_populates="owner",
    )

    sortable_fields: ClassVar[List[str]] = ["id", "email", "last_name", "role"]

    def generate_reset_token(self):
        return serializer.dumps({"id": self.id, "email": self.email, "hash": self.password})

    @staticmethod
    def generate_registration_token(email: str, role: UserRole = UserRole.CLIENT):
        return serializer.dumps({"email": email, "role": role.value.id})

    @staticmethod
    def verify_registration_token(token: str) -> Optional[tuple[str, UserRole]]:
        try:
            data = serializer.loads(token, max_age=3600)
            email = data["email"]
            role = UserRole.get(data.get("role", UserRole.CLIENT.value.id))
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        return email, role
    
    @staticmethod
    def verify_reset_token(token: str) -> Optional[tuple[int, str, str]]:
        try:
            data = serializer.loads(token, max_age=3600)
            id = data["id"]
            email = data["email"]
            hash = data["hash"]
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        return id, email, hash

    @property
    def role_type(self) -> UserRole:
        return UserRole.get(self.role)
