from typing import Optional

from sqlmodel import Field, SQLModel


class SeqRequestSampleLink(SQLModel, table=True):
    sample_id: int = Field(
        foreign_key="sample.id", primary_key=True
    )
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )
    library_id: Optional[int] = Field(
        foreign_key="library.id", nullable=True, default=None
    )


class SamplePoolLink(SQLModel, table=True):
    pool_id: int = Field(
        foreign_key="pool.id", primary_key=True
    )
    sample_id: int = Field(
        foreign_key="sample.id", primary_key=True
    )


class ExperimentLibraryLink(SQLModel, table=True):
    experiment_id: int = Field(
        foreign_key="experiment.id", primary_key=True
    )
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    lane: int = Field(nullable=False, primary_key=True)


class IndexKitLibraryType(SQLModel, table=True):
    index_kit_id: int = Field(
        foreign_key="indexkit.id", primary_key=True
    )
    library_type_id: int = Field(
        foreign_key="librarytypeid.id",
        primary_key=True
    )