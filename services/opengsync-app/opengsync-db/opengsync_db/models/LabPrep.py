from typing import TYPE_CHECKING, Optional, ClassVar

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opengsync_db.categories import LabChecklistType, LabChecklistTypeEnum, PrepStatus, PrepStatusEnum, MediaFileType, ServiceTypeEnum, ServiceType, MUXType, LibraryStatus

from .Base import Base
from . import links

if TYPE_CHECKING:
    from .User import User
    from .Library import Library
    from .Plate import Plate
    from .MediaFile import MediaFile
    from .Pool import Pool
    from .Comment import Comment


class LabPrep(Base):
    __tablename__ = "lab_prep"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    prep_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    checklist_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    service_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    creator_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    creator: Mapped["User"] = relationship("User", back_populates="preps", lazy="joined")

    plates: Mapped[list["Plate"]] = relationship("Plate", back_populates="lab_prep", cascade="save-update, merge, delete, delete-orphan", lazy="select", order_by="Plate.id")

    prep_file: Mapped[Optional["MediaFile"]] = relationship(
        "MediaFile", lazy="select", viewonly=True,
        primaryjoin=f"and_(LabPrep.id == MediaFile.lab_prep_id, MediaFile.type_id == {MediaFileType.LIBRARY_PREP_FILE.id})",
    )

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="lab_prep", lazy="select", order_by="Library.id")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="lab_prep", lazy="select")
    media_files: Mapped[list["MediaFile"]] = relationship("MediaFile", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "checklist_type_id", "service_type_id", "status_id", "num_libraries", "num_samples", "num_pools"]

    def get_checklist(self) -> dict:
        if orm.object_session(self) is None:
            raise orm.exc.DetachedInstanceError("Session must be open for checklist")
        
        libraries_added = len(self.libraries) > 0

        oligo_mux_required = any(library.mux_type in [MUXType.TENX_OLIGO, MUXType.TENX_ABC_HASH]  for library in self.libraries)
        flex_mux_required = any(library.mux_type == MUXType.TENX_FLEX_PROBE for library in self.libraries)
        on_chip_mux_required = any(library.mux_type == MUXType.TENX_ON_CHIP for library in self.libraries)

        oligo_mux_annotated = True
        flex_mux_annotated = True
        on_chip_mux_annotated = True

        oligo_mux_libraries_annotations_missing = set()
        flex_mux_libraries_annotations_missing = set()
        on_chip_mux_libraries_annotations_missing = set()

        for library in self.libraries:
            if library.mux_type is None:
                continue

            match library.mux_type:
                case MUXType.TENX_OLIGO | MUXType.TENX_ABC_HASH:
                    for link in library.sample_links:
                        _oligo_mux_annotated = all([link.mux.get(key) for key in library.mux_type.mux_columns]) if link.mux else False
                        if not _oligo_mux_annotated:
                            oligo_mux_libraries_annotations_missing.add(library.name)
                            oligo_mux_annotated = False
                case MUXType.TENX_FLEX_PROBE:
                    for link in library.sample_links:
                        _flex_mux_annotated = all([link.mux.get(key) for key in library.mux_type.mux_columns]) if link.mux else False
                        if not _flex_mux_annotated:
                            flex_mux_libraries_annotations_missing.add(library.name)
                            flex_mux_annotated = False
                case MUXType.TENX_ON_CHIP:
                    for link in library.sample_links:
                        _on_chip_mux_annotated = all([link.mux.get(key) for key in library.mux_type.mux_columns]) if link.mux else False
                        if not _on_chip_mux_annotated:
                            on_chip_mux_libraries_annotations_missing.add(library.name)
                            on_chip_mux_annotated = False
                case _:
                    continue        

        samples_pooled = (oligo_mux_required or flex_mux_required or on_chip_mux_required) if libraries_added else None
        mux_required = oligo_mux_required or flex_mux_required or on_chip_mux_required
        samples_muxed = (oligo_mux_annotated or not oligo_mux_required) and (flex_mux_annotated or not flex_mux_required) and (on_chip_mux_annotated or not on_chip_mux_required) if libraries_added else None

        if samples_pooled is False:
            for library in self.libraries:
                if library.mux_type_id is not None:
                    samples_pooled = True
                    break
                
        prep_table_submitted = (self.prep_file is not None) if (libraries_added and samples_muxed) else None

        protocols_selected = all(
            library.protocol_id is not None for library in self.libraries
        ) if (libraries_added and samples_muxed) else None

        library_fragment_sizes_measured = all(
            library.avg_fragment_size is not None for library in self.libraries
        ) if libraries_added else None

        libraries_indexed = all(
            library.is_indexed() or library.status == LibraryStatus.FAILED for library in self.libraries
        ) if libraries_added else None

        libraries_pooled = all(
            library.pool_id is not None or library.status >= LibraryStatus.SEQUENCED
            for library in self.libraries
        ) if (libraries_added and libraries_indexed) else None

        lab_prep_completed = self.status >= PrepStatus.COMPLETED if (libraries_added and libraries_pooled) else None

        return {
            "libraries_added": libraries_added,
            "samples_pooled": samples_pooled,
            "prep_table_submitted": prep_table_submitted,
            "oligo_mux_required": oligo_mux_required,
            "flex_mux_required": flex_mux_required,
            "on_chip_mux_required": on_chip_mux_required,
            "mux_required": mux_required,
            "library_fragment_sizes_measured": library_fragment_sizes_measured,
            "libraries_indexed": libraries_indexed,
            "libraries_pooled": libraries_pooled,
            "oligo_mux_annotated": oligo_mux_annotated,
            "flex_mux_annotated": flex_mux_annotated,
            "on_chip_mux_annotated": on_chip_mux_annotated,
            "oligo_mux_libraries_annotations_missing": oligo_mux_libraries_annotations_missing,
            "flex_mux_libraries_annotations_missing": flex_mux_libraries_annotations_missing,
            "on_chip_mux_libraries_annotations_missing": on_chip_mux_libraries_annotations_missing,
            "protocols_selected": protocols_selected,
            "lab_prep_completed": lab_prep_completed,
        }

    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
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
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .Sample import Sample
        from .Library import Library

        return sa.select(
            sa.func.count(sa.distinct(Sample.id))
        ).join(
            links.SampleLibraryLink, links.SampleLibraryLink.sample_id == Sample.id
        ).join(
            Library, Library.id == links.SampleLibraryLink.library_id
        ).where(
            Library.lab_prep_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

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
            return len(self.media_files)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_files' attribute.")
        
        from .MediaFile import MediaFile
        return session.query(sa.func.count(MediaFile.id)).filter(MediaFile.lab_prep_id == self.id).scalar()
    
    @num_files.expression
    def num_files(cls) -> sa.ScalarSelect[int]:
        from .MediaFile import MediaFile
        return sa.select(
            sa.func.count(MediaFile.id)
        ).where(
            MediaFile.lab_prep_id == cls.id
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
    def checklist_type(self) -> LabChecklistTypeEnum:
        return LabChecklistType.get(self.checklist_type_id)
    
    @checklist_type.setter
    def checklist_type(self, value: LabChecklistTypeEnum):
        self.checklist_type_id = value.id

    @property
    def status(self) -> PrepStatusEnum:
        return PrepStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: PrepStatusEnum):
        self.status_id = value.id

    @property
    def service_type(self) -> ServiceTypeEnum:
        return ServiceType.get(self.service_type_id)
    
    @service_type.setter
    def service_type(self, value: ServiceTypeEnum):
        self.service_type_id = value.id

    @property
    def identifier(self) -> str:
        return f"{self.checklist_type.identifier}{self.prep_number:04d}"
    
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
    
    def __repr__(self) -> str:
        return f"LabPrep(id={self.id}, name='{self.name}')"
    
    def __str__(self) -> str:
        return self.__repr__()
    
    __table_args__ = (
        sa.Index(
            "trgm_lab_prep_name_idx",
            sa.text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )