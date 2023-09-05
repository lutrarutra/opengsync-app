from typing import Optional, List, TYPE_CHECKING

from pydantic import PrivateAttr
from sqlmodel import Field, SQLModel, Relationship

from .Links import ProjectUserLink

if TYPE_CHECKING:
    from .Sample import Sample
    from .User import User


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, unique=True, index=True)
    description: str = Field(default="", max_length=1024)

    samples: List["Sample"] = Relationship(
        back_populates="project"
    )

    users: List["User"] = Relationship(
        back_populates="projects", link_model=ProjectUserLink
    )

    _num_samples: int = PrivateAttr(0)
