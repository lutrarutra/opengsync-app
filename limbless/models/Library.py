from typing import Optional, List, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship

from ..categories import LibraryType, BarcodeType
from ..tools import SearchResult
from .Links import ExperimentLibraryLink, SeqRequestLibraryLink, LibraryBarcodeLink, LibraryPoolLink

if TYPE_CHECKING:
    from .Sample import Sample
    from .Experiment import Experiment
    from .SeqRequest import SeqRequest
    from .Pool import Pool
    from .Barcode import Barcode


class Library(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    type_id: int = Field(nullable=False)
    num_pools: int = Field(nullable=False, default=0)
    
    sample_id: int = Field(nullable=False, foreign_key="sample.id")
    sample: "Sample" = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    pools: Optional["Pool"] = Relationship(
        back_populates="libraries", link_model=LibraryPoolLink,
        sa_relationship_kwargs={"lazy": "select"}
    )

    experiments: list["Experiment"] = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "select"},
        link_model=ExperimentLibraryLink
    )

    seq_requests: list["SeqRequest"] = Relationship(
        back_populates="libraries", link_model=SeqRequestLibraryLink,
        sa_relationship_kwargs={"lazy": "select"}
    )

    barcodes: list["Barcode"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "order_by": "Barcode.type_id"},
        link_model=LibraryBarcodeLink
    )

    sortable_fields: ClassVar[List[str]] = ["id", "sample_name", "type_id"]

    def to_dict(self):
        return {
            "library_id": self.id,
            "sample_name": self.sample.name,
            "library_type": self.type.value,
            "adapter": self.barcodes[0].adapter if self.barcodes else None,
        } | self.get_barcode_sequences()
    
    def get_barcodes(self) -> dict[str, "Barcode"]:
        res = {}
        for barcode in self.barcodes:
            res[BarcodeType.mapping(barcode.type_id)] = barcode
        return res
    
    def get_barcode_sequences(self) -> dict[str, str]:
        res = {}
        for barcode in self.barcodes:
            res[BarcodeType.mapping(barcode.type_id)] = barcode.sequence
        return res

    @property
    def type(self) -> LibraryType:
        return LibraryType.get(self.type_id)
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.sample.name
    
    def search_description(self) -> Optional[str]:
        return self.type.value.name
