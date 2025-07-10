from typing import Optional
from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class FileTypeEnum(DBEnum):
    dir: str
    extensions: Optional[list[str]] = None
    render_url: Optional[str] = None


class FileType(ExtendedEnum[FileTypeEnum], enum_type=FileTypeEnum):
    CUSTOM = FileTypeEnum(0, "Custom", "etc")
    SEQ_AUTH_FORM = FileTypeEnum(1, "Sequencing Authorization Form", "seq_auth_forms", ["pdf"])
    BIOANALYZER_REPORT = FileTypeEnum(2, "Bioanalyzer Report", "bioanalyzer_reports", ["pdf"])
    POST_SEQUENCING_QC_REPORT = FileTypeEnum(3, "Post-sequencing QC Report", "post_seq_qc_reports", ["pdf"])
    LANE_POOLING_TABLE = FileTypeEnum(4, "Lane Pooling Table", "lane_pooling_tables", ["tsv"])
    LIBRARY_ANNOTATION = FileTypeEnum(5, "Library Annotation", "library_annotation", ["tsv"])
    POOL_INDEXING_TABLE = FileTypeEnum(6, "Pool Indexing Table", "pool_indexing_tables", ["tsv"])
    LIBRARY_PREP_FILE = FileTypeEnum(7, "Library Prep Table", "library_prep_files", ["xlsx"])