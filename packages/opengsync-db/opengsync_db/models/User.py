from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from .Base import Base
from . import links
from ..categories import UserRole, UserRole


if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .Project import Project
    from .Pool import Pool
    from .Sample import Sample
    from .Library import Library
    from .MediaFile import MediaFile
    from .LabPrep import LabPrep
    from .APIToken import APIToken


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
    media_files: Mapped[list["MediaFile"]] = relationship("MediaFile", back_populates="uploader", lazy="select")
    preps: Mapped[list["LabPrep"]] = relationship("LabPrep", back_populates="creator", lazy="select")
    api_tokens: Mapped[list["APIToken"]] = relationship("APIToken", back_populates="owner", lazy="select", cascade="all, delete-orphan")
    assigned_projects: Mapped[list["Project"]] = relationship(
        "Project",
        secondary="project_assignee_link",
        back_populates="assignees",
        lazy="select",
    )
    assigned_seq_requests: Mapped[list["SeqRequest"]] = relationship(
        "SeqRequest",
        secondary="seq_request_assignee_link",
        back_populates="assignees",
        lazy="select",
    )

    _num_api_tokens: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_api_tokens(self) -> int:  # type: ignore[override]
        if self._num_api_tokens is not None:
            return self._num_api_tokens

        if "api_tokens" not in orm.attributes.instance_state(self).unloaded:
            return len(self.api_tokens)

        if self._is_async_context():
            raise RuntimeError(
                "_num_api_tokens was not populated via with_expression. "
                "Use orm.with_expression(User._num_api_tokens, User.num_api_tokens.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_api_tokens' attribute.")

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.api_token.select(owner_id=self.id).subquery()
        ))  # type: ignore[return-value]

    @num_api_tokens.expression
    def num_api_tokens(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .APIToken import APIToken
        return sa.select(
            sa.func.count(APIToken.uuid)
        ).where(
            *Q.api_token.where_clauses(owner_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_samples: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        if self._num_samples is not None:
            return self._num_samples

        if "samples" not in orm.attributes.instance_state(self).unloaded:
            return len(self.samples)

        if self._is_async_context():
            raise RuntimeError(
                "_num_samples was not populated via with_expression. "
                "Use orm.with_expression(User._num_samples, User.num_samples.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_samples' attribute.")

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.sample.select(user_id=self.id).subquery()
        ))  # type: ignore[return-value]

    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Sample import Sample
        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            *Q.sample.where_clauses(user_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_seq_requests: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_seq_requests(self) -> int:  # type: ignore[override]
        if self._num_seq_requests is not None:
            return self._num_seq_requests

        if "requests" not in orm.attributes.instance_state(self).unloaded:
            return len(self.requests)

        if self._is_async_context():
            raise RuntimeError(
                "_num_seq_requests was not populated via with_expression. "
                "Use orm.with_expression(User._num_seq_requests, User.num_seq_requests.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_seq_requests' attribute.")

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.seq_request.select(requestor_id=self.id).subquery()
        ))  # type: ignore[return-value]

    @num_seq_requests.expression
    def num_seq_requests(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .SeqRequest import SeqRequest
        return sa.select(
            sa.func.count(SeqRequest.id)
        ).where(
            *Q.seq_request.where_clauses(requestor_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_projects: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_projects(self) -> int:  # type: ignore[override]
        if self._num_projects is not None:
            return self._num_projects

        if "projects" not in orm.attributes.instance_state(self).unloaded:
            return len(self.projects)

        if self._is_async_context():
            raise RuntimeError(
                "_num_projects was not populated via with_expression. "
                "Use orm.with_expression(User._num_projects, User.num_projects.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_projects' attribute.")

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.project.select(owner_id=self.id).subquery()
        ))  # type: ignore[return-value]

    @num_projects.expression
    def num_projects(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Project import Project
        return sa.select(
            sa.func.count(Project.id)
        ).where(
            *Q.project.where_clauses(owner_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_affiliations: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_affiliations(self) -> int:  # type: ignore[override]
        if self._num_affiliations is not None:
            return self._num_affiliations

        if "affiliations" not in orm.attributes.instance_state(self).unloaded:
            return len(self.affiliations)

        if self._is_async_context():
            raise RuntimeError(
                "_num_affiliations was not populated via with_expression. "
                "Use orm.with_expression(User._num_affiliations, User.num_affiliations.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_affiliations' attribute.")

        return session.scalar(sa.select(sa.func.count()).select_from(
            sa.select(links.UserAffiliation).where(
                links.UserAffiliation.user_id == self.id
            ).subquery()
        ))  # type: ignore[return-value]

    @num_affiliations.expression
    def num_affiliations(cls) -> sa.ScalarSelect[int]:
        return sa.select(
            sa.func.count(links.UserAffiliation.group_id)
        ).where(
            links.UserAffiliation.user_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    def is_insider(self) -> bool:
        return self.role.insider
    
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def role(self) -> UserRole:
        return UserRole.get(self.role_id)
    
    @role.setter
    def role(self, value: UserRole):
        self.role_id = value.id
    
    @hybrid_property
    def name(self) -> str:  # type: ignore[override]
        return self.first_name + " " + self.last_name
    
    @name.expression
    def name(cls) -> sa.ScalarSelect[str]:
        return sa.select(
            sa.func.concat(cls.first_name, " ", cls.last_name)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

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
    
    @property
    def initials(self) -> str:
        return self.first_name[0] + self.last_name[0]

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