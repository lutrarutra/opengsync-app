from typing import Optional, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship
from itsdangerous import SignatureExpired, BadSignature

from .. import serializer
from ..tools import SearchResult
from ..categories import UserRole

if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .Project import Project
    from .Pool import Pool
    from .Sample import Sample
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


class User(UserMixin, SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    first_name: str = Field(nullable=False, max_length=64)
    last_name: str = Field(nullable=False, max_length=64)
    email: str = Field(nullable=False, unique=True, index=True, max_length=128)
    password: str = Field(nullable=False, max_length=128)
    role: int = Field(nullable=False)

    num_projects: int = Field(nullable=False, default=0)
    num_pools: int = Field(nullable=False, default=0)
    num_samples: int = Field(nullable=False, default=0)
    num_seq_requests: int = Field(nullable=False, default=0)

    requests: list["SeqRequest"] = Relationship(
        back_populates="requestor",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    projects: list["Project"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    pools: list["Pool"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    samples: list["Sample"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    libraries: list["Library"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    sortable_fields: ClassVar[list[str]] = ["id", "email", "last_name", "role", "num_projects", "num_pool", "num_samples", "num_seq_requests"]

    def is_insider(self) -> bool:
        return self.role_type in UserRole.insiders

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
    
    @property
    def name(self) -> str:
        return self.first_name + " " + self.last_name

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.first_name + " " + self.last_name
    
    def search_description(self) -> Optional[str]:
        return self.email
