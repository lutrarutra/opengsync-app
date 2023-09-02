from typing import Optional, List

from sqlmodel import Field, SQLModel, Relationship

class SeqKit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True, unique=True)

    seq_indices: List["SeqIndex"] = Relationship(back_populates="seq_kit")