from typing import Optional, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from .index_kit import index_kit
    from .SeqIndex import SeqIndex


class SeqAdapter(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=128, index=True)

    index_kit_id: int = Field(nullable=False, foreign_key="index_kit.id")
    index_kit: "index_kit" = Relationship(
        back_populates="adapters",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    indices: list["SeqIndex"] = Relationship(
        back_populates="adapter",
        sa_relationship_kwargs={"lazy": "joined"},
    )