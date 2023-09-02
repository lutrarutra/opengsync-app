from typing import Optional, List

from sqlmodel import Field, SQLModel, Relationship

class SeqIndex(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sequence: str = Field(nullable=False, max_length=128, index=True)
    type: str = Field(nullable=False, max_length=64, index=True)
    adapter: str = Field(nullable=False, max_length=128, index=True)

    seq_kit_id: int = Field(nullable=False, foreign_key="indexkit.id")
    seq_kit: "IndexKit" = Relationship(back_populates="seq_indices")

    def __str__(self):
        return f"SeqIndex('{self.sequence}', {self.type})"
    
    def __repr__(self) -> str:
        return str(self)