from typing import Optional
from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class FileTypeEnum(DBEnum):
    dir: str
    extensions: Optional[list[str]] = None


class FileType(ExtendedEnum[FileTypeEnum], enum_type=FileTypeEnum):
    CUSTOM = FileTypeEnum(0, "Custom", "etc")
    SEQ_AUTH_FORM = FileTypeEnum(1, "Sequencing Authorization Form", "seq_auth_forms", ["pdf"])
    BIOANALYZER_REPORT = FileTypeEnum(2, "Bioanalyzer Report", "bioanalyzer_reports", ["pdf"])
    POST_SEQUENCING_QC_REPORT = FileTypeEnum(3, "Post-sequencing QC Report", "post_seq_qc_reports", ["pdf"])