from datetime import datetime
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base
from ..categories import SeqRequestStatus, ReadType, DataDeliveryMode, SubmissionType, MediaFileType, LibraryType, MUXType
from . import links

if TYPE_CHECKING:
    from .Library import Library
    from .User import User
    from .Contact import Contact
    from .Pool import Pool
    from .MediaFile import MediaFile
    from .Comment import Comment
    from .Sample import Sample
    from .Event import Event
    from .Group import Group
    from .DataPath import DataPath
    from .Project import Project


class SeqRequest(Base):
    __tablename__ = "seq_request"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)

    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.String(1024), nullable=True)
    special_requirements: Mapped[Optional[str]] = mapped_column(sa.String(1024), nullable=True)
    billing_code: Mapped[Optional[str]] = mapped_column(sa.String(256), nullable=True)
    
    data_delivery_mode_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    read_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    submission_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=SeqRequestStatus.DRAFT.id)

    timestamp_submitted_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)
    timestamp_finished_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)

    read_length: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    num_lanes: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    organization_contact_id: Mapped[int] = mapped_column(sa.ForeignKey("contact.id"), nullable=False)
    organization_contact: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[organization_contact_id], cascade="save-update, merge")

    requestor_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    requestor: Mapped["User"] = relationship("User", back_populates="requests", lazy="select", foreign_keys=[requestor_id])

    group_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("group.id"), nullable=True)
    group: Mapped[Optional["Group"]] = relationship("Group", back_populates="seq_requests", lazy="select", foreign_keys=[group_id], cascade="save-update, merge")

    bioinformatician_contact_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("contact.id"), nullable=True)
    bioinformatician_contact: Mapped[Optional["Contact"]] = relationship("Contact", lazy="select", foreign_keys=[bioinformatician_contact_id], cascade="save-update, merge")
    
    contact_person_id: Mapped[int] = mapped_column(sa.ForeignKey("contact.id"), nullable=False)
    contact_person: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[contact_person_id], cascade="save-update, merge")

    billing_contact_id: Mapped[int] = mapped_column(sa.ForeignKey("contact.id"), nullable=False)
    billing_contact: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[billing_contact_id], cascade="save-update, merge")

    seq_auth_form_file: Mapped[Optional["MediaFile"]] = relationship(
        "MediaFile", lazy="select", viewonly=True, uselist=False,
        primaryjoin=f"and_(SeqRequest.id == MediaFile.seq_request_id, MediaFile.type_id == {MediaFileType.SEQ_AUTH_FORM.id})",
    )

    sample_submission_event_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("event.id"), nullable=True)
    sample_submission_event: Mapped[Optional["Event"]] = relationship("Event", lazy="select", foreign_keys=[sample_submission_event_id], back_populates="seq_request", cascade="save-update, merge, delete")

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="seq_request", lazy="select", cascade="all, delete-orphan")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="seq_request", lazy="select",)
    media_files: Mapped[list["MediaFile"]] = relationship("MediaFile", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")
    delivery_email_links: Mapped[list[links.SeqRequestDeliveryEmailLink]] = relationship("SeqRequestDeliveryEmailLink", lazy="select", cascade="all, save-update, delete, merge", back_populates="seq_request")
    samples: Mapped[list["Sample"]] = relationship(
        "Sample", viewonly=True,
        secondary="join(SampleLibraryLink, Sample, SampleLibraryLink.sample_id == Sample.id).join(Library, Library.id == SampleLibraryLink.library_id)",
        primaryjoin="SeqRequest.id == Library.seq_request_id",
    )
    sample_library_links: Mapped[list["links.SampleLibraryLink"]] = relationship(
        "links.SampleLibraryLink", viewonly=True,
        secondary="join(Library, SampleLibraryLink, Library.id == SampleLibraryLink.library_id)",
        primaryjoin="SeqRequest.id == Library.seq_request_id",
    )
    assignees: Mapped[list["User"]] = relationship(
        "User",
        secondary="seq_request_assignee_link",
        back_populates="assigned_seq_requests",
        lazy="select",
    )
    data_paths: Mapped[list["DataPath"]] = relationship("DataPath", back_populates="seq_request", lazy="select")

    review_checklist: Mapped[dict[str, bool] | None] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None)

    def get_submit_checklist(self) -> dict:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open for checklist")
        
        samples_added = self.num_samples > 0 and self.num_libraries > 0
        authorization_form_added = self.seq_auth_form_file is not None
        is_submittable = self.is_submittable()
        request_submitted = self.status >= SeqRequestStatus.SUBMITTED if samples_added else None

        return dict(
            samples_added=samples_added,
            authorization_form_added=authorization_form_added,
            is_submittable=is_submittable,
            request_submitted=request_submitted,
        )
    
    def get_review_checklist(self) -> dict[str, bool]:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open for checklist")
        
        checklist = {}
        if self.review_checklist is not None:
            checklist.update(self.review_checklist)

        checklist["technical_requirements"] = checklist.get("technical_requirements", False)
        checklist["check_libraries"] = checklist.get("check_libraries", False)
        checklist["check_multiplexing"] = checklist.get("check_multiplexing", False)
        checklist["check_overview"] = checklist.get("check_overview", False)
        checklist["check_contacts"] = checklist.get("check_contacts", False)
        checklist["check_comments"] = checklist.get("check_comments", False)
        checklist["samples_checked"] = checklist.get("samples_checked", False)
        checklist["check_submission_date"] = checklist.get("check_submission_date", False)
        checklist["check_barcodes"] = checklist.get("check_barcodes", True if self.submission_type not in [SubmissionType.POOLED_LIBRARIES, SubmissionType.UNPOOLED_LIBRARIES] else False)
        checklist["auth_form_checked"] = checklist.get("auth_form_checked", None if self.seq_auth_form_file is None else False)
        checklist["submission_processed"] = self.status > SeqRequestStatus.SUBMITTED

        return checklist
    
    @property
    def projects(self) -> list["Project"]:
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'projects' attribute.")
        
        from .. import queries as Q
        from .Project import Project

        return session.query(Project).where(
            *Q.project.where_clauses(seq_request_id=self.id)
        ).all()
    
    @hybrid_property
    def num_projects(self) -> int:  # type: ignore[override]
        if self._num_projects is not None:
            return self._num_projects

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_projects.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_projects was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_projects, SeqRequest.num_projects.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.project.select(seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_projects.expression
    def num_projects(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Project import Project

        return sa.select(
            sa.func.count(sa.distinct(Project.id))
        ).where(
            *Q.project.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_libraries(self) -> int:  # type: ignore[override]
        if self._num_libraries is not None:
            return self._num_libraries
        
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return len(self.libraries)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_libraries.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_libraries was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_libraries, SeqRequest.num_libraries.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.library.select(seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_libraries.expression
    def num_libraries(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Library import Library
        return sa.select(
            sa.func.count(Library.id)
        ).where(
            *Q.library.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_pools(self) -> int:  # type: ignore[override]
        if self._num_pools is not None:
            return self._num_pools

        if "pools" not in orm.attributes.instance_state(self).unloaded:
            return len(self.pools)

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_pools.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_pools was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_pools, SeqRequest.num_pools.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.pool.select(seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_pools.expression
    def num_pools(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Pool import Pool
        return sa.select(
            sa.func.count(Pool.id)
        ).where(
            *Q.pool.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        if self._num_samples is not None:
            return self._num_samples

        if "samples" not in orm.attributes.instance_state(self).unloaded:
            return len(self.samples)

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_samples.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_samples was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_samples, SeqRequest.num_samples.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.sample.select(seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Sample import Sample
        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            *Q.sample.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_assignees: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_assignees(self) -> int:  # type: ignore[override]
        if self._num_assignees is not None:
            return self._num_assignees

        if "assignees" not in orm.attributes.instance_state(self).unloaded:
            return len(self.assignees)

        if self._is_async_context():
            raise RuntimeError(
                "_num_assignees was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_assignees, SeqRequest.num_assignees.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_assignees.")

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.user.select(assignees_seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]

    @num_assignees.expression
    def num_assignees(cls) -> sa.ScalarSelect[int]:
        from .User import User
        from .. import queries as Q
        return sa.select(
            sa.func.count(User.id)
        ).where(
            *Q.user.where_clauses(assignees_seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_comments(self) -> int:  # type: ignore[override]
        if self._num_comments is not None:
            return self._num_comments

        if "comments" not in orm.attributes.instance_state(self).unloaded:
            return len(self.comments)

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_comments.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_comments was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_comments, SeqRequest.num_comments.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.comment.select(seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_comments.expression
    def num_comments(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Comment import Comment
        return sa.select(
            sa.func.count(Comment.id)
        ).where(
            *Q.comment.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_files(self) -> int:  # type: ignore[override]
        if self._num_files is not None:
            return self._num_files

        if "files" not in orm.attributes.instance_state(self).unloaded:
            return len(self.media_files)

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_files.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_files was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_files, SeqRequest.num_files.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.media_file.select(seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_files.expression
    def num_files(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .MediaFile import MediaFile
        return sa.select(
            sa.func.count(MediaFile.id)
        ).where(
            *Q.media_file.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_data_paths(self) -> int:  # type: ignore[override]
        if self._num_data_paths is not None:
            return self._num_data_paths

        if "data_paths" not in orm.attributes.instance_state(self).unloaded:
            return len(self.data_paths)

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_data_paths.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_data_paths was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_data_paths, SeqRequest.num_data_paths.expression) "
                "in your query options."
            )

        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.data_path.select(seq_request_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_data_paths.expression
    def num_data_paths(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .DataPath import DataPath
        return sa.select(
            sa.func.count(DataPath.id)
        ).where(
            *Q.data_path.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _library_types: Mapped[list[int] | None] = orm.query_expression()

    @hybrid_property
    def library_types(self) -> list[LibraryType]:  # type: ignore[override]
        if self._library_types is not None:
            return [LibraryType.get(type_id) for type_id in self._library_types]

        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            types = set()
            for lib in self.libraries:
                types.add(lib.type_id)
            return [LibraryType.get(type_id) for type_id in sorted(types)]

        if self._is_async_context():
            raise RuntimeError(
                "_library_types was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._library_types, SeqRequest.library_types.expression) "
                "in your query options."
            )

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'library_types' attribute.")

        from .. import queries as Q
        from .Library import Library
        result = session.scalar(sa.select(
            sa.func.array_agg(sa.distinct(Library.type_id))
        ).select_from(
            Q.library.select(seq_request_id=self.id).subquery()
        ))
        if result is None:
            return []
        return [LibraryType.get(type_id) for type_id in result]

    @library_types.expression
    def library_types(cls):
        from .. import queries as Q
        from .Library import Library
        return sa.select(
            sa.func.coalesce(
                sa.func.array_agg(sa.distinct(Library.type_id)),
                sa.cast(sa.text("'{}'"), sa.ARRAY(sa.Integer))
            )
        ).where(
            *Q.library.where_clauses(seq_request_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @property
    def mux_types(self) -> list[MUXType]:
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return list(set(library.mux_type for library in self.libraries if library.mux_type is not None))
        
        from .Library import Library
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_libraries' attribute.")
        
        mux_type_ids = session.query(Library.mux_type_id).where(
            (Library.seq_request_id == self.id) &
            Library.mux_type_id.isnot(None)
        ).distinct().all()

        return [MUXType.get(mux_type_id) for (mux_type_id,) in mux_type_ids]
    
    @hybrid_property
    def library_type_counts(self) -> dict[LibraryType, int]:
        counts: dict[LibraryType, int] = {}
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            for lib in self.libraries:
                lib_type = LibraryType.get(lib.type_id)
                counts[lib_type] = counts.get(lib_type, 0) + 1
            return counts
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'library_type_counts' attribute.")
        from .Library import Library
        results = session.query(Library.type_id, sa.func.count(Library.id)).filter(Library.seq_request_id == self.id).group_by(Library.type_id).all()
        for type_id, count in results:
            lib_type = LibraryType.get(type_id)
            counts[lib_type] = count
        return counts
    
    @hybrid_property
    def num_delivery_email_links(self) -> int:  # type: ignore[override]
        if self._num_delivery_email_links is not None:
            return self._num_delivery_email_links

        if "delivery_email_links" not in orm.attributes.instance_state(self).unloaded:
            return len(self.delivery_email_links)

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_delivery_email_links.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_delivery_email_links was not populated via with_expression. "
                "Use orm.with_expression(SeqRequest._num_delivery_email_links, SeqRequest.num_delivery_email_links.expression) "
                "in your query options."
            )
        
        return session.scalar(sa.select(sa.func.count()).select_from(
            sa.select(links.SeqRequestDeliveryEmailLink).where(
                links.SeqRequestDeliveryEmailLink.seq_request_id == self.id
            ).subquery()
        ))  # type: ignore[return-value]
    
    @num_delivery_email_links.expression
    def num_delivery_email_links(cls) -> sa.ScalarSelect[int]:
        return sa.select(
            sa.func.count(links.SeqRequestDeliveryEmailLink.email)
        ).where(
            links.SeqRequestDeliveryEmailLink.seq_request_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @property
    def status(self) -> SeqRequestStatus:
        return SeqRequestStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: SeqRequestStatus):
        self.status_id = value.id
    
    @property
    def submission_type(self) -> SubmissionType:
        return SubmissionType.get(self.submission_type_id)
    
    @submission_type.setter
    def submission_type(self, value: SubmissionType):
        self.submission_type_id = value.id
    
    @property
    def data_delivery_mode(self) -> DataDeliveryMode:
        return DataDeliveryMode.get(self.data_delivery_mode_id)
    
    @data_delivery_mode.setter
    def data_delivery_mode(self, value: DataDeliveryMode):
        self.data_delivery_mode_id = value.id
    
    @property
    def read_type(self) -> ReadType:
        return ReadType.get(self.read_type_id)
    
    @read_type.setter
    def read_type(self, value: ReadType):
        self.read_type_id = value.id
    
    @property
    def timestamp_submitted(self) -> datetime | None:
        if self.timestamp_submitted_utc is None:
            return None
        return localize(self.timestamp_submitted_utc)
    
    @property
    def timestamp_finished(self) -> datetime | None:
        if self.timestamp_finished_utc is None:
            return None
        return localize(self.timestamp_finished_utc)
    
    def is_indexed(self) -> bool:
        for library in self.libraries:
            if not library.is_indexed():
                return False
            
        return True
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def is_editable(self) -> bool:
        return self.status == SeqRequestStatus.DRAFT
    
    def is_authorized(self) -> bool:
        return self.seq_auth_form_file is not None
    
    def is_submittable(self) -> bool:
        return self.status == SeqRequestStatus.DRAFT and self.num_libraries > 0 and self.is_authorized()
    
    def timestamp_submitted_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        if (ts := self.timestamp_submitted) is None:
            return ""
        return ts.strftime(fmt)
    
    def timestamp_finished_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        if (ts := self.timestamp_finished) is None:
            return ""
        return ts.strftime(fmt)
    
    def __str__(self):
        return f"SeqRequest(id: {self.id}, name:{self.name})"
    
    def __repr__(self) -> str:
        return str(self)
    
    @property
    def identifier(self) -> str:
        return f"BSR_{self.id:04d}"
    
    _num_libraries: Mapped[int | None] = orm.query_expression()
    _num_projects: Mapped[int | None] = orm.query_expression()
    _num_pools: Mapped[int | None] = orm.query_expression()
    _num_samples: Mapped[int | None] = orm.query_expression()
    _num_comments: Mapped[int | None] = orm.query_expression()
    _num_files: Mapped[int | None] = orm.query_expression()
    _num_data_paths: Mapped[int | None] = orm.query_expression()
    _num_delivery_email_links: Mapped[int | None] = orm.query_expression()
    
    __table_args__ = (
        sa.Index(
            "trgm_seq_request_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )