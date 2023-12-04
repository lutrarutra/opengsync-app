from typing import Optional, List, TYPE_CHECKING, ClassVar, Union

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
    num_seq_requests: int = Field(nullable=False, default=0)
    submitted: bool = Field(nullable=False, default=False)
    kit: str = Field(nullable=False, default="custom", max_length=64)

    volume: Optional[int] = Field(nullable=True, default=None)
    dna_concentration: Optional[float] = Field(nullable=True, default=None)
    total_size: Optional[int] = Field(nullable=True, default=None)

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
        sa_relationship_kwargs={"lazy": "selectin"},
        link_model=LibraryBarcodeLink
    )

    sortable_fields: ClassVar[List[str]] = ["id", "sample_name", "type_id", "owner_id"]

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
    
    def get_barcode_with_type(self, barcode_type: Union[int, BarcodeType]) -> Optional["Barcode"]:
        if isinstance(barcode_type, BarcodeType):
            barcode_type = barcode_type.value.id
        
        for barcode in self.barcodes:
            if barcode.type_id == barcode_type:
                return barcode
        return None
    
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
    
    def is_editable(self) -> bool:
        return not self.submitted
