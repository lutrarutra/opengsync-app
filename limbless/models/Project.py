from typing import Optional, List, TYPE_CHECKING

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from .Sample import Sample
    from .User import User


class Project(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, index=True)
    description: str = Field(default="", max_length=1024)

    samples: List["Sample"] = Relationship(
        back_populates="project"
    )

    owner_id: int = Field(nullable=False, foreign_key="user.id")
    owner: "User" = Relationship(
        back_populates="projects",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    _num_samples: int = PrivateAttr(0)
