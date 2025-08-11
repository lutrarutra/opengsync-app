from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .Base import Base
from . import links
from ..categories import UserRole, UserRoleEnum


if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .Project import Project
    from .Pool import Pool
    from .Sample import Sample
    from .Library import Library
    from .File import File
    from .LabPrep import LabPrep


class UserMixin():
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
            return str(self.id)  # type: ignore
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


class User(Base, UserMixin):
    __tablename__ = "lims_user"     # type: ignore

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    email: Mapped[str] = mapped_column(sa.String(128), nullable=False, unique=True, index=True)
    password: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    role_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    affiliations: Mapped[list[links.UserAffiliation]] = relationship("UserAffiliation", back_populates="user", lazy="select", cascade="all, save-update, merge")
    requests: Mapped[list["SeqRequest"]] = relationship("SeqRequest", back_populates="requestor", lazy="select")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner", lazy="select")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="owner", lazy="select")
    samples: Mapped[list["Sample"]] = relationship("Sample", back_populates="owner", lazy="select")
    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="owner", lazy="select")
    files: Mapped[list["File"]] = relationship("File", back_populates="uploader", lazy="select")
    preps: Mapped[list["LabPrep"]] = relationship("LabPrep", back_populates="creator", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "email", "last_name", "role_id", "num_projects", "num_samples", "num_projects", "num_seq_requests"]

    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        return len(self.samples)
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .Sample import Sample
        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            Sample.owner_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_seq_requests(self) -> int:  # type: ignore[override]
        return len(self.requests)
    
    @num_seq_requests.expression
    def num_seq_requests(cls) -> sa.ScalarSelect[int]:
        from .SeqRequest import SeqRequest
        return sa.select(
            sa.func.count(SeqRequest.id)
        ).where(
            SeqRequest.requestor_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_projects(self) -> int:  # type: ignore[override]
        return len(self.projects)
    
    @num_projects.expression
    def num_projects(cls) -> sa.ScalarSelect[int]:
        from .Project import Project
        return sa.select(
            sa.func.count(Project.id)
        ).where(
            Project.owner_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    def is_insider(self) -> bool:
        return self.role.is_insider()
    
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def generate_reset_token(self, serializer: URLSafeTimedSerializer) -> str:
        return str(serializer.dumps({"id": self.id, "email": self.email, "hash": self.password}))

    @staticmethod
    def generate_registration_token(email: str, serializer: URLSafeTimedSerializer, role: UserRoleEnum = UserRole.CLIENT) -> str:
        return str(serializer.dumps({"email": email, "role": role.id}))

    @staticmethod
    def verify_registration_token(token: str, serializer: URLSafeTimedSerializer) -> tuple[str, UserRoleEnum] | None:
        try:
            data = serializer.loads(token, max_age=3600)
            email = data["email"]
            role = UserRole.get(data.get("role", UserRole.CLIENT.id))
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        return email, role
    
    @staticmethod
    def verify_reset_token(token: str, serializer: URLSafeTimedSerializer) -> tuple[int, str, str] | None:
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
    def role(self) -> UserRoleEnum:
        return UserRole.get(self.role_id)
    
    @property
    def name(self) -> str:
        return self.first_name + " " + self.last_name

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.first_name + " " + self.last_name
    
    def search_description(self) -> str:
        return self.email
    
    def __str__(self) -> str:
        return f"User(id={self.id}, email={self.email})"
    
    def __repr__(self) -> str:
        return str(self)

    __table_args__ = (
        sa.Index(
            "trgm_lims_user_email_idx",
            sa.text("lower(email) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        sa.Index(
            "trgm_lims_user_first_name_idx",
            sa.text("lower(first_name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        sa.Index(
            "trgm_lims_user_last_name_idx",
            sa.text("lower(last_name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        sa.Index(
            "trgm_lims_user_full_name_idx",
            sa.text("lower(first_name || ' ' || last_name) gin_trgm_ops"),
            postgresql_using="gin",
        )
    )