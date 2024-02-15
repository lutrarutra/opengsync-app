from typing import Optional, TYPE_CHECKING
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from .User import User


class Comment(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    text: str = Field(nullable=False, max_length=512)
    timestamp: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    author_id: int = Field(nullable=False, foreign_key="lims_user.id")
    file_id: Optional[int] = Field(nullable=True, foreign_key="file.id")

    author: "User" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    def timestamp_to_str(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d %H:%M')
    
    def date(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d')
    
    def time(self) -> str:
        return self.timestamp.strftime('%H:%M')