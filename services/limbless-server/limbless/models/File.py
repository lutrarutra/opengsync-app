import os
from typing import Optional

from sqlmodel import Field, SQLModel, Relationship

from ..categories import FileType
from .User import User


class File(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64)
    extension: str = Field(nullable=False, max_length=16)
    type_id: int = Field(nullable=False)
    description: Optional[str] = Field(nullable=True, max_length=256)
    uuid: str = Field(nullable=False, max_length=64)
    
    uploader_id: int = Field(nullable=False, foreign_key="lims_user.id")
    uploader: "User" = Relationship(
        back_populates="files",
        sa_relationship_kwargs={"lazy": "select"}
    )

    @property
    def type(self) -> FileType:
        return FileType.get(self.type_id)
    
    @property
    def path(self) -> str:
        return os.path.join(self.type.value.description, f"{self.uuid}.{self.extension}")