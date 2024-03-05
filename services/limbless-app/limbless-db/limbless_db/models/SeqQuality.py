from typing import Optional, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

from sqlalchemy import BigInteger, Column

if TYPE_CHECKING:
    from .Library import Library
    from .Experiment import Experiment


class SeqQuality(SQLModel, table=True):
    library_id: int = Field(nullable=False, foreign_key="library.id", primary_key=True)
    experiment_id: int = Field(nullable=False, foreign_key="experiment.id", primary_key=True)
    lane: int = Field(nullable=False, primary_key=True)
    
    num_lane_reads: int = Field(nullable=False, sa_column=Column(BigInteger()))
    num_total_reads: int = Field(nullable=False, sa_column=Column(BigInteger()))
    
    mean_quality_pf_r1: Optional[float] = Field(nullable=True)
    q30_perc_r1: Optional[float] = Field(nullable=True)

    mean_quality_pf_r2: Optional[float] = Field(nullable=True)
    q30_perc_r2: Optional[float] = Field(nullable=True)

    mean_quality_pf_i1: Optional[float] = Field(nullable=True)
    q30_perc_i1: Optional[float] = Field(nullable=True)

    mean_quality_pf_i2: Optional[float] = Field(nullable=True)
    q30_perc_i2: Optional[float] = Field(nullable=True)

    library: "Library" = Relationship(
        back_populates="read_qualities",
        sa_relationship_kwargs={"lazy": "select"}
    )

    experiment: "Experiment" = Relationship(
        back_populates="read_qualities",
        sa_relationship_kwargs={"lazy": "select"}
    )