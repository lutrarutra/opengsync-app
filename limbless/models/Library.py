from typing import Optional, List, TYPE_CHECKING, ClassVar
from dataclasses import dataclass

from sqlmodel import Field, SQLModel, Relationship

from ..categories import LibraryType
from .Links import SeqRequestLibraryLink, LibraryPoolLink

if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .Pool import Pool
    from .Links import SampleLibraryLink
    from .CMO import CMO
    from .User import User
    from .Sample import Sample


@dataclass
class Index:
    sequence: Optional[str]
    adapter: Optional[str]


class Library(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64)
    type_id: int = Field(nullable=False)
    num_pools: int = Field(nullable=False, default=0)
    num_samples: int = Field(nullable=False, default=0)
    num_seq_requests: int = Field(nullable=False, default=0)
    submitted: bool = Field(nullable=False, default=False)
    kit: str = Field(nullable=False, default="custom", max_length=64)

    volume: Optional[int] = Field(nullable=True, default=None)
    dna_concentration: Optional[float] = Field(nullable=True, default=None)
    total_size: Optional[int] = Field(nullable=True, default=None)

    sample_id: Optional[int] = Field(nullable=True, foreign_key="sample.id")
    sample: Optional["Sample"] = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    owner_id: int = Field(nullable=False, foreign_key="user.id")
    owner: "User" = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    sample_links: list["SampleLibraryLink"] = Relationship(
        back_populates="library",
        sa_relationship_kwargs={"lazy": "select"}
    )

    cmos: list["CMO"] = Relationship(
        back_populates="library",
        sa_relationship_kwargs={"lazy": "select"}
    )

    pools: Optional["Pool"] = Relationship(
        back_populates="libraries", link_model=LibraryPoolLink,
        sa_relationship_kwargs={"lazy": "select"}
    )

    seq_requests: list["SeqRequest"] = Relationship(
        back_populates="libraries", link_model=SeqRequestLibraryLink,
        sa_relationship_kwargs={"lazy": "select"}
    )

    index_1_sequence: Optional[str] = Field(nullable=True)
    index_2_sequence: Optional[str] = Field(nullable=True)
    index_3_sequence: Optional[str] = Field(nullable=True)
    index_4_sequence: Optional[str] = Field(nullable=True)

    index_1_adapter: Optional[str] = Field(nullable=True)
    index_2_adapter: Optional[str] = Field(nullable=True)
    index_3_adapter: Optional[str] = Field(nullable=True)
    index_4_adapter: Optional[str] = Field(nullable=True)

    sortable_fields: ClassVar[List[str]] = ["id", "name", "type_id", "owner_id"]

    def to_dict(self):
        return {
            "library_id": self.id,
            "library_type": self.type.value,
        }

    @property
    def type(self) -> LibraryType:
        return LibraryType.get(self.type_id)
    
    def is_multiplexed(self) -> bool:
        return self.num_samples > 1
    
    def is_editable(self) -> bool:
        return not self.submitted
    
    @property
    def indices(self) -> List[Optional[Index]]:
        return [
            Index(self.index_1_sequence, self.index_1_adapter) if self.index_1_sequence is not None else None,
            Index(self.index_2_sequence, self.index_2_adapter) if self.index_2_sequence is not None else None,
            Index(self.index_3_sequence, self.index_3_adapter) if self.index_3_sequence is not None else None,
            Index(self.index_4_sequence, self.index_4_adapter) if self.index_4_sequence is not None else None,
        ]

    def is_indexed(self) -> bool:
        return self.index_1_sequence is not None