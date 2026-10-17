from opengsync_db import categories as C

from .EditKitBarcodes import EditKitBarcodesForm
from .EditSingleIndexKitBarcodes import EditSingleIndexKitBarcodes
from .EditDualIndexKitBarcodes import EditDualIndexKitBarcodes
from .EditCombinatorialKitBarcodes import EditCombinatorialKitBarcodes
from .EditKitTENXATACBarcodes import EditKitTENXATACBarcodes

EDIT_KIT_BARCODES_ACTIONS: dict[C.IndexType, type[EditKitBarcodesForm]] = {
    C.IndexType.SINGLE_INDEX_I7: EditSingleIndexKitBarcodes,
    C.IndexType.DUAL_INDEX: EditDualIndexKitBarcodes,
    C.IndexType.COMBINATORIAL_DUAL_INDEX: EditCombinatorialKitBarcodes,
    C.IndexType.TENX_ATAC_INDEX: EditKitTENXATACBarcodes,
}

__all__ = [
    "EditKitBarcodesForm",
    "EditSingleIndexKitBarcodes",
    "EditDualIndexKitBarcodes",
    "EditCombinatorialKitBarcodes",
    "EditKitTENXATACBarcodes",
    "EDIT_KIT_BARCODES_ACTIONS",
]
