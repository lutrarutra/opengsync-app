from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opengsync_db.categories import LabChecklistType, PrepStatus, MediaFileType, ServiceType, MUXType, LibraryStatus, LibraryType

from .Base import Base

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
    creator: Mapped["User"] = relationship("User", back_populates="preps", lazy="select")

    plates: Mapped[list["Plate"]] = relationship("Plate", back_populates="lab_prep", cascade="save-update, merge, delete, delete-orphan", lazy="select", order_by="Plate.id")

    prep_file: Mapped[Optional["MediaFile"]] = relationship(
        "MediaFile", lazy="select", viewonly=True,
        primaryjoin=f"and_(LabPrep.id == MediaFile.lab_prep_id, MediaFile.type_id == {MediaFileType.LIBRARY_PREP_FILE.id})",
    )

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="lab_prep", lazy="select", order_by="Library.id")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="lab_prep", lazy="select")
    media_files: Mapped[list["MediaFile"]] = relationship("MediaFile", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")

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
    
    @property
    def mux_types(self) -> list[MUXType]:
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return list(set(library.mux_type for library in self.libraries if library.mux_type is not None))
        
        from .Library import Library
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_libraries' attribute.")
        
        mux_type_ids = session.query(Library.mux_type_id).where(
            (Library.lab_prep_id == self.id) &
            Library.mux_type_id.isnot(None)
        ).distinct().all()

        return [MUXType.get(mux_type_id) for (mux_type_id,) in mux_type_ids]
    
    @hybrid_property
    def library_types(self) -> list[LibraryType]:
        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            types = set()
            for lib in self.libraries:
                types.add(lib.type_id)

            return [LibraryType.get(type_id) for type_id in sorted(types)]
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'library_types' attribute.")
        from .Library import Library
        type_ids = session.query(Library.type_id).filter(Library.lab_prep_id == self.id).distinct().order_by(Library.type_id).all()
        return [LibraryType.get(type_id) for (type_id,) in type_ids]

    @hybrid_property
    def num_samples(self) -> int:  # type: ignore[override]
        if self._num_samples is not None:
            return self._num_samples

        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_libraries' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_samples was not populated via with_expression. "
                "Use orm.with_expression(LabPrep._num_samples, LabPrep.num_samples.expression) "
                "in your query options."
            )
        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.sample.select(lab_prep_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_samples.expression
    def num_samples(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Sample import Sample

        return sa.select(
            sa.func.count(Sample.id)
        ).where(
            *Q.sample.where_clauses(lab_prep_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_samples: Mapped[int | None] = orm.query_expression()

    @hybrid_property
    def num_libraries(self) -> int:  # type: ignore[override]
        if self._num_libraries is not None:
            return self._num_libraries

        if "libraries" not in orm.attributes.instance_state(self).unloaded:
            return len(self.libraries)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_libraries' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_libraries was not populated via with_expression. "
                "Use orm.with_expression(LabPrep._num_libraries, LabPrep.num_libraries.expression) "
                "in your query options."
            )
        
        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.library.select(lab_prep_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_libraries.expression
    def num_libraries(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Library import Library
        return sa.select(
            sa.func.count(Library.id)
        ).where(
            *Q.library.where_clauses(lab_prep_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_libraries: Mapped[int | None] = orm.query_expression()
    
    @hybrid_property
    def num_pools(self) -> int:  # type: ignore[override]
        if self._num_pools is not None:
            return self._num_pools

        if "pools" not in orm.attributes.instance_state(self).unloaded:
            return len(self.pools)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_pools' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_pools was not populated via with_expression. "
                "Use orm.with_expression(LabPrep._num_pools, LabPrep.num_pools.expression) "
                "in your query options."
            )
        
        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.pool.select(lab_prep_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_pools.expression
    def num_pools(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Pool import Pool
        return sa.select(
            sa.func.count(Pool.id)
        ).where(
            *Q.pool.where_clauses(lab_prep_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_pools: Mapped[int | None] = orm.query_expression()
    
    @hybrid_property
    def num_files(self) -> int:  # type: ignore[override]
        if self._num_files is not None:
            return self._num_files

        if "files" not in orm.attributes.instance_state(self).unloaded:
            return len(self.media_files)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_files' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_files was not populated via with_expression. "
                "Use orm.with_expression(LabPrep._num_files, LabPrep.num_files.expression) "
                "in your query options."
            )
        
        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.media_file.select(lab_prep_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_files.expression
    def num_files(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .MediaFile import MediaFile
        return sa.select(
            sa.func.count(MediaFile.id)
        ).where(
            *Q.media_file.where_clauses(lab_prep_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_files: Mapped[int | None] = orm.query_expression()
    
    @hybrid_property
    def num_comments(self) -> int:  # type: ignore[override]
        if self._num_comments is not None:
            return self._num_comments

        if "comments" not in orm.attributes.instance_state(self).unloaded:
            return len(self.comments)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_comments' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_comments was not populated via with_expression. "
                "Use orm.with_expression(LabPrep._num_comments, LabPrep.num_comments.expression) "
                "in your query options."
            )
        
        from .. import queries as Q
        return session.scalar(sa.select(sa.func.count()).select_from(
            Q.comment.select(lab_prep_id=self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_comments.expression
    def num_comments(cls) -> sa.ScalarSelect[int]:
        from .. import queries as Q
        from .Comment import Comment
        return sa.select(
            sa.func.count(Comment.id)
        ).where(
            *Q.comment.where_clauses(lab_prep_id=cls.id)
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_comments: Mapped[int | None] = orm.query_expression()
    
    @hybrid_property
    def num_plates(self) -> int:  # type: ignore[override]
        if self._num_plates is not None:
            return self._num_plates

        if "plates" not in orm.attributes.instance_state(self).unloaded:
            return len(self.plates)
        
        if (session := orm.object_session(self)) is None:
            raise orm.exc.DetachedInstanceError("Session detached, cannot access 'num_plates' attribute.")

        if self._is_async_context():
            raise RuntimeError(
                "_num_plates was not populated via with_expression. "
                "Use orm.with_expression(LabPrep._num_plates, LabPrep.num_plates.expression) "
                "in your query options."
            )
        
        from .Plate import Plate
        return session.scalar(sa.select(sa.func.count()).select_from(
            sa.select(Plate).where(Plate.lab_prep_id == self.id).subquery()
        ))  # type: ignore[return-value]
    
    @num_plates.expression
    def num_plates(cls) -> sa.ScalarSelect[int]:
        from .Plate import Plate
        return sa.select(
            sa.func.count(Plate.id)
        ).where(
            Plate.lab_prep_id == cls.id
        ).correlate(cls).scalar_subquery()  # type: ignore[arg-type]

    _num_plates: Mapped[int | None] = orm.query_expression()
    
    @property
    def checklist_type(self) -> LabChecklistType:
        return LabChecklistType.get(self.checklist_type_id)
    
    @checklist_type.setter
    def checklist_type(self, value: LabChecklistType):
        self.checklist_type_id = value.id

    @property
    def status(self) -> PrepStatus:
        return PrepStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: PrepStatus):
        self.status_id = value.id

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.get(self.service_type_id)
    
    @service_type.setter
    def service_type(self, value: ServiceType):
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