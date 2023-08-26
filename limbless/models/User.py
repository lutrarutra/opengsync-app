from typing import Optional, List

from sqlmodel import Field, SQLModel, Relationship

from .Links import ProjectUserLink

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(nullable=False, unique=True, index=True, max_length=128)
    password_hash: str = Field(nullable=False, max_length=128)
    role: int = Field(nullable=False)

    projects: List["Project"] = Relationship(
        back_populates="users", link_model=ProjectUserLink
    )