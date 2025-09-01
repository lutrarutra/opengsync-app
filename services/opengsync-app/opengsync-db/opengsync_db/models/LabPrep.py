from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opengsync_db.categories import LabProtocol, LabProtocolEnum, PrepStatus, PrepStatusEnum, FileType, AssayTypeEnum, AssayType

from .Base import Base
from .. import LAB_PROTOCOL_START_NUMBER
from . import links

if TYPE_CHECKING:
    from .User import User
    from .Library import Library
    from .Plate import Plate
    from .File import File
    from .Pool import Pool
    from .Comment import Comment


class LabPrep(Base):
    __tablename__ = "lab_prep"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    prep_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    protocol_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    assay_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    creator_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    creator: Mapped["User"] = relationship("User", back_populates="preps", lazy="joined")

    plates: Mapped[list["Plate"]] = relationship("Plate", back_populates="lab_prep", cascade="save-update, merge, delete, delete-orphan", lazy="select", order_by="Plate.id")

    prep_file: Mapped[Optional["File"]] = relationship(
        "File", lazy="select", viewonly=True,
        primaryjoin=f"and_(LabPrep.id == File.lab_prep_id, File.type_id == {FileType.LIBRARY_PREP_FILE.id})",
    )

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="lab_prep", lazy="select", order_by="Library.id")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="lab_prep", lazy="select")
    files: Mapped[list["File"]] = relationship("File", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")

    @property
    def num_samples(self) -> int:
        from .Sample import Sample
        from .Library import Library
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_libraries' attribute.")

        return session.query(Sample.id).where(
            sa.exists().where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.lab_prep_id == self.id)
            )
        ).count()

    @hybrid_property
    def num_libraries(self) -> int:  # type: ignore[override]
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return len(self.libraries)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_libraries' attribute.")
        
        from .Library import Library
        return session.query(sa.func.count(Library.id)).filter(Library.lab_prep_id == self.id).scalar()
    
    @num_libraries.expression
    def num_libraries(cls) -> sa.ScalarSelect[int]:
        from .Library import Library
        return sa.select(
            sa.func.count(Library.id)
        ).where(
            Library.lab_prep_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_pools(self) -> int:  # type: ignore[override]
        if "pools" not in orm.attributes.instance_state(self).unloaded:
            return len(self.pools)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_pools' attribute.")
        
        from .Pool import Pool
        return session.query(sa.func.count(Pool.id)).filter(Pool.lab_prep_id == self.id).scalar()
    
    @num_pools.expression
    def num_pools(cls) -> sa.ScalarSelect[int]:
        from .Pool import Pool
        return sa.select(
            sa.func.count(Pool.id)
        ).where(
            Pool.lab_prep_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_files(self) -> int:  # type: ignore[override]
        if "files" not in orm.attributes.instance_state(self).unloaded:
            return len(self.files)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_files' attribute.")
        
        from .File import File
        return session.query(sa.func.count(File.id)).filter(File.lab_prep_id == self.id).scalar()
    
    @num_files.expression
    def num_files(cls) -> sa.ScalarSelect[int]:
        from .File import File
        return sa.select(
            sa.func.count(File.id)
        ).where(
            File.lab_prep_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_comments(self) -> int:  # type: ignore[override]
        if "comments" not in orm.attributes.instance_state(self).unloaded:
            return len(self.comments)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_comments' attribute.")
        
        from .Comment import Comment
        return session.query(sa.func.count(Comment.id)).filter(Comment.lab_prep_id == self.id).scalar()
    
    @num_comments.expression
    def num_comments(cls) -> sa.ScalarSelect[int]:
        from .Comment import Comment
        return sa.select(
            sa.func.count(Comment.id)
        ).where(
            Comment.lab_prep_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @hybrid_property
    def num_plates(self) -> int:  # type: ignore[override]
        if "plates" not in orm.attributes.instance_state(self).unloaded:
            return len(self.plates)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_plates' attribute.")
        
        from .Plate import Plate
        return session.query(sa.func.count(Plate.id)).filter(Plate.lab_prep_id == self.id).scalar()
    
    @num_plates.expression
    def num_plates(cls) -> sa.ScalarSelect[int]:
        from .Plate import Plate
        return sa.select(
            sa.func.count(Plate.id)
        ).where(
            Plate.lab_prep_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]
    
    @property
    def protocol(self) -> LabProtocolEnum:
        return LabProtocol.get(self.protocol_id)
    
    @protocol.setter
    def protocol(self, value: LabProtocolEnum):
        self.protocol_id = value.id

    @property
    def status(self) -> PrepStatusEnum:
        return PrepStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: PrepStatusEnum):
        self.status_id = value.id

    @property
    def assay_type(self) -> AssayTypeEnum:
        return AssayType.get(self.assay_type_id)
    
    @assay_type.setter
    def assay_type(self, value: AssayTypeEnum):
        self.assay_type_id = value.id

    @property
    def identifier(self) -> str:
        return f"{self.protocol.identifier}{self.prep_number + LAB_PROTOCOL_START_NUMBER:04d}"
    
    @property
    def display_name(self) -> str:
        if self.name == self.identifier:
            return self.name
        
        return f"{self.name} [{self.identifier}]"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> str:
        return self.identifier
    
    __table_args__ = (
        sa.Index(
            "trgm_lab_prep_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )