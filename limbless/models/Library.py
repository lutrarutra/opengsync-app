from typing import Optional, List, TYPE_CHECKING, ClassVar, Union

from sqlmodel import Field, SQLModel, Relationship

from ..categories import LibraryType, BarcodeType
from ..tools import SearchResult
from .Links import ExperimentLibraryLink, SeqRequestLibraryLink, LibraryBarcodeLink, LibraryPoolLink
from .User import User

if TYPE_CHECKING:
    from .Experiment import Experiment
    from .SeqRequest import SeqRequest
    from .Pool import Pool
    from .Barcode import Barcode
    from .Links import SampleLibraryLink
    from .CMO import CMO


class Library(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    type_id: int = Field(nullable=False)
    num_pools: int = Field(nullable=False, default=0)
    num_samples: int = Field(nullable=False, default=0)
    num_seq_requests: int = Field(nullable=False, default=0)
    submitted: bool = Field(nullable=False, default=False)
    kit: str = Field(nullable=False, default="custom", max_length=64)

    volume: Optional[int] = Field(nullable=True, default=None)
    dna_concentration: Optional[float] = Field(nullable=True, default=None)
    total_size: Optional[int] = Field(nullable=True, default=None)

    owner_id: int = Field(nullable=False, foreign_key="user.id")
    owner: "User" = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    sample_links: list["SampleLibraryLink"] = Relationship(
        back_populates="library",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    cmos: list["CMO"] = Relationship(
        back_populates="library",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    pools: Optional["Pool"] = Relationship(
        back_populates="libraries", link_model=LibraryPoolLink,
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    experiments: list["Experiment"] = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "selectin"},
        link_model=ExperimentLibraryLink
    )

    seq_requests: list["SeqRequest"] = Relationship(
        back_populates="libraries", link_model=SeqRequestLibraryLink,
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    barcodes: list["Barcode"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"},
        link_model=LibraryBarcodeLink
    )

    sortable_fields: ClassVar[List[str]] = ["id", "sample_name", "type_id", "owner_id"]

    def to_dict(self):
        return {
            "library_id": self.id,
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
    
    def is_multiplexed(self) -> bool:
        return self.num_samples > 1
    
    def is_editable(self) -> bool:
        return not self.submitted
