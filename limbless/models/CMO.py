from typing import Optional, List, TYPE_CHECKING, ClassVar, Union

from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library


class CMO(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    sequence: str = Field(nullable=False, max_length=64)
    pattern: str = Field(nullable=False, max_length=32)
    read: str = Field(nullable=False, max_length=16)

    sample_id: int = Field(nullable=False, foreign_key="sample.id")
    sample: "Sample" = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    library_id: int = Field(nullable=False, foreign_key="library.id")
    library: "Library" = Relationship(
        back_populates="cmos",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
