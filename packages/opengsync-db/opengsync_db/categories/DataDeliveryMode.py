from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class DataDeliveryModeEnum(DBEnum):
    label: str
    description: str


class DataDeliveryMode(ExtendedEnum):
    label: str
    description: str
    CUSTOM = DataDeliveryModeEnum(0, "Custom", "I am not sure...")
    READS_ONLY = DataDeliveryModeEnum(1, "Reads only", "We will provide you with the raw reads (fastq/bam-files).")
    ALIGNMENT = DataDeliveryModeEnum(2, "Alignment", "In addition to raw reads, we will provide you with the aligned reads (bam-files).")
    CELLRANGER_ANALYSIS = DataDeliveryModeEnum(3, "CellRanger analysis", "In addition to raw reads, we will provide you with the CellRanger analysis output. 10X Only.")
    DOWNSTREAM = DataDeliveryModeEnum(4, "Downstream analysis", "We will provide you with the results of the downstream analysis. Pick this option only if we have agreed on a collaboration project beforehand.")

    @property
    def display_name(self) -> str:
        return self.label
