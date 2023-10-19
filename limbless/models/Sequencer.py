from typing import Optional, TYPE_CHECKING

from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


class Sequencer(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)

    name: str = Field(nullable=False, max_length=64, unique=True, index=True)
    ip: Optional[str] = Field(nullable=True, max_length=128, unique=False)
