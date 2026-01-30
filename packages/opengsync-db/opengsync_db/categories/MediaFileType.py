from typing import Optional
from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class MediaFileTypeEnum(DBEnum):
    label: str
    dir: str
    extensions: Optional[list[str]] = None
    render_url: str | None = None


class MediaFileType(ExtendedEnum):
    label: str
    dir: str
    extensions: Optional[list[str]]
    render_url: str | None
    
    CUSTOM = MediaFileTypeEnum(0, "Custom", "etc")
    SEQ_AUTH_FORM = MediaFileTypeEnum(1, "Sequencing Authorization Form", "seq_auth_forms", ["pdf"])
    BIOANALYZER_REPORT = MediaFileTypeEnum(2, "Bioanalyzer Report", "bioanalyzer_reports", ["pdf"])
    POST_SEQUENCING_QC_REPORT = MediaFileTypeEnum(3, "Post-sequencing QC Report", "post_seq_qc_reports", ["pdf"])
    LANE_POOLING_TABLE = MediaFileTypeEnum(4, "Lane Pooling Table", "lane_sample_pooling_tables", ["tsv"])
    LIBRARY_ANNOTATION = MediaFileTypeEnum(5, "Library Annotation", "library_annotation", ["tsv"])
    POOL_INDEXING_TABLE = MediaFileTypeEnum(6, "Pool Indexing Table", "pool_indexing_tables", ["tsv"])
    LIBRARY_PREP_FILE = MediaFileTypeEnum(7, "Library Prep Table", "library_prep_files", ["xlsx"])