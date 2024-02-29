from typing import Optional, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

from ..core.categories import DeliveryStatus

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library
    from .CMO import CMO
    from .Experiment import Experiment
    from .Pool import Pool


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
    cmo: Optional["CMO"] = Relationship()

    def __str__(self) -> str:
        return f"SampleLibraryLink(sample_id: {self.sample_id}, library_id: {self.library_id}, cmo_id: {self.cmo_id})"


class ExperimentPoolLink(SQLModel, table=True):
    experiment_id: int = Field(
        foreign_key="experiment.id", primary_key=True
    )
    pool_id: int = Field(
        foreign_key="pool.id", primary_key=True
    )
    lane: int = Field(nullable=False, primary_key=True)

    experiment: "Experiment" = Relationship()
    pool: "Pool" = Relationship()

    def __str__(self) -> str:
        return f"ExperimentPoolLink(experiment_id: {self.experiment_id}, pool_id: {self.pool_id}, lane: {self.lane})"


class SeqRequestExperimentLink(SQLModel, table=True):
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )
    experiment_id: int = Field(
        foreign_key="experiment.id", primary_key=True
    )

    def __str__(self) -> str:
        return f"SeqRequestExperimentLink(seq_request_id: {self.seq_request_id}, experiment_id: {self.experiment_id})"
    

class ExperimentFileLink(SQLModel, table=True):
    file_id: int = Field(
        foreign_key="file.id", primary_key=True
    )
    experiment_id: int = Field(
        foreign_key="experiment.id", primary_key=True
    )
    

class SeqRequestFileLink(SQLModel, table=True):
    file_id: int = Field(
        foreign_key="file.id", primary_key=True
    )
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )


class ExperimentCommentLink(SQLModel, table=True):
    experiment_id: int = Field(
        foreign_key="experiment.id", primary_key=True
    )
    comment_id: int = Field(
        foreign_key="comment.id", primary_key=True
    )


class SeqRequestCommentLink(SQLModel, table=True):
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )
    comment_id: int = Field(
        foreign_key="comment.id", primary_key=True
    )


class LibraryFeatureLink(SQLModel, table=True):
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    feature_id: int = Field(
        foreign_key="feature.id", primary_key=True
    )


class SeqRequestShareEmailLink(SQLModel, table=True):
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )
    email: str = Field(primary_key=True, max_length=128)
    
    status_id: int = Field(nullable=False, default=0)

    @property
    def status(self) -> DeliveryStatus:
        return DeliveryStatus.get(self.status_id)