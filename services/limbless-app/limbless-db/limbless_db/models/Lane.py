from typing import Optional, TYPE_CHECKING, ClassVar

from sqlmodel import Field, SQLModel, Relationship

from .Links import LanePoolLink

if TYPE_CHECKING:
    from .Experiment import Experiment
    from .Pool import Pool


class Lane(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    number: int = Field(nullable=False)
    phi_x: Optional[float] = Field(nullable=True, default=None)

    experiment_id: int = Field(nullable=False, foreign_key="experiment.id")
    experiment: "Experiment" = Relationship(
        back_populates="lanes",
        sa_relationship_kwargs={"lazy": "select"}
    )

    pools: list["Pool"] = Relationship(
        link_model=LanePoolLink, back_populates="lanes",
        sa_relationship_kwargs={"lazy": "select"},
    )

    sortable_fields: ClassVar[list[str]] = ["id", "number", "experiment_id", "phi_x"]
