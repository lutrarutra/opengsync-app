from typing import Optional, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship

from ..categories import PoolStatus, PoolStatusEnum
from ..core.SearchResult import SearchResult
from .Links import LanePoolLink

if TYPE_CHECKING:
    from .Library import Library
    from .User import User
    from .Experiment import Experiment
    from .SeqRequest import SeqRequest
    from .Lane import Lane


class Pool(SQLModel, SearchResult, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True)
    status_id: int = Field(nullable=False, default=0)
    num_m_reads_requested: Optional[float] = Field(default=None, nullable=True)
    
    num_libraries: int = Field(nullable=False, default=0)

    owner_id: int = Field(nullable=False, foreign_key="lims_user.id")
    owner: "User" = Relationship(
        back_populates="pools",
        sa_relationship_kwargs={"lazy": "joined"}
    )
    libraries: list["Library"] = Relationship(
        back_populates="pool",
        sa_relationship_kwargs={"lazy": "select"},
    )

    lanes: list["Lane"] = Relationship(
        link_model=LanePoolLink, back_populates="pools",
        sa_relationship_kwargs={"lazy": "select"},
    )
    
    experiment_id: int = Field(nullable=True, foreign_key="experiment.id", default=None)
    experiment: "Experiment" = Relationship(
        back_populates="pools",
        sa_relationship_kwargs={"lazy": "select"},
    )

    seq_request_id: Optional[int] = Field(nullable=True, foreign_key="seqrequest.id")
    seq_request: Optional["SeqRequest"] = Relationship(
        sa_relationship_kwargs={"lazy": "select"}
    )

    contact_name: str = Field(nullable=False, max_length=128)
    contact_email: str = Field(nullable=False, max_length=128)
    contact_phone: Optional[str] = Field(nullable=True, max_length=16)

    sortable_fields: ClassVar[list[str]] = ["id", "name", "owner_id", "num_libraries", "num_m_reads_requested"]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
        }
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return ""
    
    def list_library_types(self) -> list[str]:
        return list(set([library.type.abbreviation for library in self.libraries]))
    
    @property
    def status(self) -> PoolStatusEnum:
        return PoolStatus.get(self.status_id)