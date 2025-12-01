from datetime import datetime
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base
from ..categories import SeqRequestStatus, SeqRequestStatusEnum, ReadType, ReadTypeEnum, DataDeliveryMode, DataDeliveryModeEnum, SubmissionType, SubmissionTypeEnum, MediaFileType, LibraryType, LibraryTypeEnum
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
    requestor: Mapped["User"] = relationship("User", back_populates="requests", lazy="joined", foreign_keys=[requestor_id])

    group_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("group.id"), nullable=True)
    group: Mapped[Optional["Group"]] = relationship("Group", back_populates="seq_requests", lazy="joined", foreign_keys=[group_id], cascade="save-update, merge")

    bioinformatician_contact_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("contact.id"), nullable=True)
    bioinformatician_contact: Mapped[Optional["Contact"]] = relationship("Contact", lazy="select", foreign_keys=[bioinformatician_contact_id], cascade="save-update, merge")
    
    contact_person_id: Mapped[int] = mapped_column(sa.ForeignKey("contact.id"), nullable=False)
    contact_person: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[contact_person_id], cascade="save-update, merge")

    billing_contact_id: Mapped[int] = mapped_column(sa.ForeignKey("contact.id"), nullable=False)
    billing_contact: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[billing_contact_id], cascade="save-update, merge")

    seq_auth_form_file: Mapped[Optional["MediaFile"]] = relationship(
        "MediaFile", lazy="joined", viewonly=True, uselist=False,
        primaryjoin=f"and_(SeqRequest.id == MediaFile.seq_request_id, MediaFile.type_id == {MediaFileType.SEQ_AUTH_FORM.id})",
    )

    sample_submission_event_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("event.id"), nullable=True)
    sample_submission_event: Mapped[Optional["Event"]] = relationship("Event", lazy="select", foreign_keys=[sample_submission_event_id], back_populates="seq_request", cascade="save-update, merge, delete")

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="seq_request", lazy="select")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="seq_request", lazy="select",)
    media_files: Mapped[list["MediaFile"]] = relationship("MediaFile", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")
    delivery_email_links: Mapped[list[links.SeqRequestDeliveryEmailLink]] = relationship("SeqRequestDeliveryEmailLink", lazy="select", cascade="all, save-update, delete, merge", back_populates="seq_request")
    samples: Mapped[list["Sample"]] = relationship(
        "Sample", viewonly=True,
        secondary="join(SampleLibraryLink, Sample, SampleLibraryLink.sample_id == Sample.id).join(Library, Library.id == SampleLibraryLink.library_id)",
        primaryjoin="SeqRequest.id == Library.seq_request_id",
    )
    assignees: Mapped[list["User"]] = relationship(
        "User",
        secondary="seq_request_assignee_link",
        back_populates="assigned_seq_requests",
        lazy="select",
    )
    data_paths: Mapped[list["DataPath"]] = relationship("DataPath", back_populates="seq_request", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "status_id", "requestor_id", "timestamp_submitted_utc", "timestamp_finished_utc", "num_libraries"]

    def get_checklist(self) -> dict:
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
    
    @property
    def projects(self) -> list["Project"]:
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'projects' attribute.")
        
        from .Project import Project
        from .Sample import Sample
        from .Library import Library

        return session.query(Project).where(
            sa.exists().where(
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == self.id)
            )
        ).all()
    
    @hybrid_property
    def num_projects(self) -> int:  # type: ignore[override]        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_projects.")

        from .Project import Project
        from .Sample import Sample
        from .Library import Library

        return session.query(sa.func.count(sa.distinct(Project.id))).where(
            sa.exists().where(
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == self.id)
            )
        ).scalar()
    
    @num_projects.expression
    def num_projects(cls) -> sa.ScalarSelect[int]:
        from .Project import Project
        from .Sample import Sample
        from .Library import Library

        return sa.select(
            sa.func.count(sa.distinct(Project.id))
        ).where(
            sa.exists().where(
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == cls.id)
            )
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_libraries(self) -> int:  # type: ignore[override]
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return len(self.libraries)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_libraries.")

        from .Library import Library
        return session.query(sa.func.count(Library.id)).filter(Library.seq_request_id == self.id).scalar()
    
    @num_libraries.expression
    def num_libraries(cls) -> sa.ScalarSelect[int]:
        from .Library import Library
        return sa.select(
            sa.func.count(Library.id)
        ).where(
            Library.seq_request_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_pools(self) -> int:  # type: ignore[override]
        if "pools" not in orm.attributes.instance_state(self).unloaded:
            return len(self.pools)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_pools.")
        from .Pool import Pool
        return session.query(sa.func.count(Pool.id)).filter(Pool.seq_request_id == self.id).scalar()
    
    @num_pools.expression
    def num_pools(cls) -> sa.ScalarSelect[int]:
        from .Pool import Pool
        return sa.select(
            sa.func.count(Pool.id)
        ).where(
            Pool.seq_request_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        if "samples" not in orm.attributes.instance_state(self).unloaded:
            return len(self.samples)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_samples.")
        from .Sample import Sample
        from .Library import Library
        return session.query(sa.func.count(Sample.id)).where(
            sa.exists().where(
                sa.and_(
                    links.SampleLibraryLink.sample_id == Sample.id,
                    Library.id == links.SampleLibraryLink.library_id,
                    Library.seq_request_id == self.id
                )
            )
        ).scalar()
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .Sample import Sample
        from .Library import Library
        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            sa.exists().where(
                sa.and_(
                    links.SampleLibraryLink.sample_id == Sample.id,
                    Library.id == links.SampleLibraryLink.library_id,
                    Library.seq_request_id == cls.id
                )
            )
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_assignees(self) -> int:  # type: ignore[override]
        if "assignees" not in orm.attributes.instance_state(self).unloaded:
            return len(self.assignees)
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_assignees.")
        from .User import User
        return session.query(sa.func.count(User.id)).join(links.SeqRequestAssigneeLink
        ).filter(links.SeqRequestAssigneeLink.seq_request_id == self.id).scalar()
    
    @hybrid_property
    def num_comments(self) -> int:  # type: ignore[override]
        if "comments" not in orm.attributes.instance_state(self).unloaded:
            return len(self.comments)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_comments.")
        from .Comment import Comment
        return session.query(sa.func.count(Comment.id)).filter(Comment.seq_request_id == self.id).scalar()
    
    @num_comments.expression
    def num_comments(cls) -> sa.ScalarSelect[int]:
        from .Comment import Comment
        return sa.select(
            sa.func.count(Comment.id)
        ).where(
            Comment.seq_request_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_files(self) -> int:  # type: ignore[override]
        if "files" not in orm.attributes.instance_state(self).unloaded:
            return len(self.media_files)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_files.")
        from .MediaFile import MediaFile
        return session.query(sa.func.count(MediaFile.id)).filter(MediaFile.seq_request_id == self.id).scalar()
    
    @num_files.expression
    def num_files(cls) -> sa.ScalarSelect[int]:
        from .MediaFile import MediaFile
        return sa.select(
            sa.func.count(MediaFile.id)
        ).where(
            MediaFile.seq_request_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @hybrid_property
    def num_data_paths(self) -> int:  # type: ignore[override]
        if "data_paths" not in orm.attributes.instance_state(self).unloaded:
            return len(self.data_paths)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_data_paths.")
        from .DataPath import DataPath
        return session.query(sa.func.count(DataPath.id)).filter(DataPath.seq_request_id == self.id).scalar()
    
    @num_data_paths.expression
    def num_data_paths(cls) -> sa.ScalarSelect[int]:
        from .DataPath import DataPath
        return sa.select(
            sa.func.count(DataPath.id)
        ).where(
            DataPath.seq_request_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def library_types(self) -> list[LibraryTypeEnum]:
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            types = set()
            for lib in self.libraries:
                types.add(lib.type_id)

            return [LibraryType.get(type_id) for type_id in sorted(types)]
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'library_types' attribute.")
        from .Library import Library
        type_ids = session.query(Library.type_id).filter(Library.seq_request_id == self.id).distinct().order_by(Library.type_id).all()
        return [LibraryType.get(type_id) for (type_id,) in type_ids]
    
    @hybrid_property
    def library_type_counts(self) -> dict[LibraryTypeEnum, int]:
        counts: dict[LibraryTypeEnum, int] = {}
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
        if "delivery_email_links" not in orm.attributes.instance_state(self).unloaded:
            return len(self.delivery_email_links)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session is detached, cannot query num_delivery_email_links.")
        
        return session.query(links.SeqRequestDeliveryEmailLink).where(links.SeqRequestDeliveryEmailLink.seq_request_id == self.id).count()
    
    @num_delivery_email_links.expression
    def num_delivery_email_links(cls) -> sa.ScalarSelect[int]:
        return sa.select(
            sa.func.count(links.SeqRequestDeliveryEmailLink.email)
        ).where(
            links.SeqRequestDeliveryEmailLink.seq_request_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    @property
    def status(self) -> SeqRequestStatusEnum:
        return SeqRequestStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: SeqRequestStatusEnum):
        self.status_id = value.id
    
    @property
    def submission_type(self) -> SubmissionTypeEnum:
        return SubmissionType.get(self.submission_type_id)
    
    @submission_type.setter
    def submission_type(self, value: SubmissionTypeEnum):
        self.submission_type_id = value.id
    
    @property
    def data_delivery_mode(self) -> DataDeliveryModeEnum:
        return DataDeliveryMode.get(self.data_delivery_mode_id)
    
    @data_delivery_mode.setter
    def data_delivery_mode(self, value: DataDeliveryModeEnum):
        self.data_delivery_mode_id = value.id
    
    @property
    def read_type(self) -> ReadTypeEnum:
        return ReadType.get(self.read_type_id)
    
    @read_type.setter
    def read_type(self, value: ReadTypeEnum):
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
    
    __table_args__ = (
        sa.Index(
            "trgm_seq_request_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )