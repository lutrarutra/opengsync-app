from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class DataDeliveryModeEnum(DBEnum):
    description: str


class DataDeliveryMode(ExtendedEnum[DataDeliveryModeEnum], enum_type=DataDeliveryModeEnum):
    CUSTOM = DataDeliveryModeEnum(0, "Custom", "I am not sure...")
    READS_ONLY = DataDeliveryModeEnum(1, "Reads only", "We will provide you with the raw reads (fastq-files).")
    ALIGNMENT = DataDeliveryModeEnum(2, "Alignment", "We will provide you with the aligned reads (bam-files).")
    CELLRANGER_ANALYSIS = DataDeliveryModeEnum(3, "CellRanger analysis", "In addition to fastq-files, we will provide you with the CellRanger analysis output. 10X Only.")
    DOWNSTREAM = DataDeliveryModeEnum(4, "Downstream analysis", "We will provide you with the results of the downstream analysis. Pick this option only if we have agreed on a collaboration project beforehand.")
