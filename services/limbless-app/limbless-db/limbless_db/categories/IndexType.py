from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum
from .BarcodeType import BarcodeTypeEnum, BarcodeType


@dataclass
class IndexTypeEnum(DBEnum):
    config: list[tuple[BarcodeTypeEnum, int]]


class IndexType(ExtendedEnum[IndexTypeEnum], enum_type=IndexTypeEnum):
    DUAL_INDEX = IndexTypeEnum(1, "Dual Index", [(BarcodeType.INDEX_I7, 1), (BarcodeType.INDEX_I5, 1)])
    SINGLE_INDEX = IndexTypeEnum(2, "Single Index", [(BarcodeType.INDEX_I7, 1), (BarcodeType.INDEX_I5, 1)])
    TENX_ATAC_INDEX = IndexTypeEnum(3, "10x ATAC Index", [(BarcodeType.INDEX_I7, 4)])
