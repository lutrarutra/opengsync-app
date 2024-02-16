from typing import TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library


class CMO(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    sequence: str = Field(nullable=False, max_length=32)
    pattern: str = Field(nullable=False, max_length=32)
    read: str = Field(nullable=False, max_length=8)

    sample_id: int = Field(nullable=False, foreign_key="sample.id")
    sample: "Sample" = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    library_id: int = Field(nullable=False, foreign_key="library.id")
    library: "Library" = Relationship(
        back_populates="cmos",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    def __str__(self) -> str:
        return f"CMO(id: {self.id}, sequence: {self.sequence}, pattern: {self.pattern}, read: {self.read}, sample_id: {self.sample_id}, library_id: {self.library_id})"