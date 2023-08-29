from typing import Optional
from enum import Enum

from sqlmodel import Field, SQLModel

class Organism(SQLModel, table=True):
    tax_id: int = Field(default=None, primary_key=True)
    scientific_name: str = Field(nullable=False, max_length=128, index=True)
    common_name: Optional[str] = Field(nullable=True, max_length=128, index=True)
    category: int = Field(nullable=False)