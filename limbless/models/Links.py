from typing import Optional, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library
    from .CMO import CMO


class SeqRequestLibraryLink(SQLModel, table=True):
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )


class SampleLibraryLink(SQLModel, table=True):
    sample_id: int = Field(
        foreign_key="sample.id", primary_key=True
    )
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    cmo_id: Optional[int] = Field(
        foreign_key="cmo.id", primary_key=False,
        nullable=True, default=None
    )

    sample: "Sample" = Relationship(back_populates="library_links")
    library: "Library" = Relationship(back_populates="sample_links")
    cmo: "CMO" = Relationship()

    def __str__(self):
        return f"SampleLibraryLink(sample_id: {self.sample_id}, library_id: {self.library_id}, cmo_id: {self.cmo_id})"


class LibraryPoolLink(SQLModel, table=True):
    pool_id: int = Field(
        foreign_key="pool.id", primary_key=True
    )
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )


class ExperimentLibraryLink(SQLModel, table=True):
    experiment_id: int = Field(
        foreign_key="experiment.id", primary_key=True
    )
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    lane: int = Field(nullable=False, primary_key=True)


class LibraryBarcodeLink(SQLModel, table=True):
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    barcode_id: int = Field(
        foreign_key="barcode.id", primary_key=True
    )