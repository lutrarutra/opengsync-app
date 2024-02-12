from typing import Optional

from sqlmodel import Field, SQLModel


class SeqQuality(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    library_id: int = Field(nullable=False, foreign_key="library.id")
    lane: int = Field(nullable=False)
    
    num_lane_reads: int = Field(nullable=False)
    num_total_reads: int = Field(nullable=False)
    mean_quality_pf_total: float = Field(nullable=False)
    q30_perc_total: float = Field(nullable=False)
    
    num_r1_reads: Optional[int] = Field(nullable=True)
    mean_quality_pf_r1: Optional[float] = Field(nullable=True)
    q30_perc_r1: Optional[float] = Field(nullable=True)

    num_r2_reads: Optional[int] = Field(nullable=True)
    mean_quality_pf_r2: Optional[float] = Field(nullable=True)
    q30_perc_r2: Optional[float] = Field(nullable=True)

    num_i1_reads: Optional[int] = Field(nullable=True)
    mean_quality_pf_i1: Optional[float] = Field(nullable=True)
    q30_perc_i1: Optional[float] = Field(nullable=True)

    num_i2_reads: Optional[int] = Field(nullable=True)
    mean_quality_pf_i2: Optional[float] = Field(nullable=True)
    q30_perc_i2: Optional[float] = Field(nullable=True)