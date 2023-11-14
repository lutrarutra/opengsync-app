from sqlmodel import Field, SQLModel


class SeqRequestLibraryLink(SQLModel, table=True):
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )


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