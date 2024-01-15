from typing import Optional, List, TYPE_CHECKING, ClassVar
from dataclasses import dataclass

from sqlmodel import Field, SQLModel, Relationship

from ..categories import LibraryType
from .Links import SeqRequestLibraryLink

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
    
    submitted: bool = Field(nullable=False, default=False)

    volume: Optional[int] = Field(nullable=True, default=None)
    dna_concentration: Optional[float] = Field(nullable=True, default=None)
    total_size: Optional[int] = Field(nullable=True, default=None)

    pool_id: Optional[int] = Field(nullable=True, foreign_key="pool.id")
    pool: Optional["Pool"] = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    # num_pools: int = Field(nullable=False, default=0)
    num_samples: int = Field(nullable=False, default=0)
    num_seq_requests: int = Field(nullable=False, default=0)

    sample_id: int = Field(nullable=True, foreign_key="sample.id")
    sample: "Sample" = Relationship(
        back_populates="libraries",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    owner_id: int = Field(nullable=False, foreign_key="lims_user.id")
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

    # pools: Optional["Pool"] = Relationship(
    #     back_populates="libraries", link_model=LibraryPoolLink,
    #     sa_relationship_kwargs={"lazy": "select"}
    # )

    seq_requests: list["SeqRequest"] = Relationship(
        back_populates="libraries", link_model=SeqRequestLibraryLink,
        sa_relationship_kwargs={"lazy": "select"}
    )

    index_1_sequence: Optional[str] = Field(nullable=True)
    index_2_sequence: Optional[str] = Field(nullable=True)
    index_3_sequence: Optional[str] = Field(nullable=True)
    index_4_sequence: Optional[str] = Field(nullable=True)

    adapter: Optional[str] = Field(nullable=True)

    sortable_fields: ClassVar[List[str]] = ["id", "name", "type_id", "owner_id", "pool_id"]

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
            Index(self.index_1_sequence, self.adapter) if self.index_1_sequence is not None else None,
            Index(self.index_2_sequence, self.adapter) if self.index_2_sequence is not None else None,
            Index(self.index_3_sequence, self.adapter) if self.index_3_sequence is not None else None,
            Index(self.index_4_sequence, self.adapter) if self.index_4_sequence is not None else None,
        ]

    def is_indexed(self) -> bool:
        return self.index_1_sequence is not None
    
    def is_pooled(self) -> bool:
        return self.pool_id is not None