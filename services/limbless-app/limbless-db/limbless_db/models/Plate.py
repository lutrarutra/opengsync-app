from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from .Sample import Sample
from .Library import Library
from .Pool import Pool

if TYPE_CHECKING:
    from .User import User


class Plate(Base):
    __tablename__ = "plate"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    num_cols: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    num_rows: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    owner_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", lazy="joined")

    samples: Mapped[list[Sample]] = relationship("Sample", back_populates="plate", lazy="select")
    libraries: Mapped[list[Library]] = relationship("Library", back_populates="plate", lazy="select")
    pools: Mapped[list[Pool]] = relationship("Pool", back_populates="plate", lazy="select")
        
    def __str__(self) -> str:
        return f"Plate(id: {self.id}, name: {self.name}, num_cols: {self.num_cols}, num_rows: {self.num_rows})"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    @staticmethod
    def well_identifier(i: int, num_cols: int, num_rows: int, flipped: bool = False) -> str:
        if flipped:
            if i >= num_cols * num_rows:
                raise ValueError(f"Index {i} is out of bounds for a {num_rows}x{num_cols} plate")
            col = i // num_rows
            row = i % num_rows
        else:
            if i >= num_cols * num_rows:
                raise ValueError(f"Index {i} is out of bounds for a {num_cols}x{num_rows} plate")
            row = i // num_cols
            col = i % num_cols
        
        return f"{chr(ord('A') + row)}{col + 1}"
    
    def get_well(self, i: int, flipped: bool = False) -> str:
        return Plate.well_identifier(i, self.num_cols, self.num_cols, flipped)
    
    def get_well_xy(self, row: int, col: int) -> str:
        return Plate.well_identifier(row * self.num_cols + col, self.num_cols, self.num_cols)
    
    def get_sample(self, well: str) -> Optional[Library | Sample | Pool]:
        for sample in self.samples:
            if sample.plate_well == well:
                return sample
        for library in self.libraries:
            if library.plate_well == well:
                return library
        for pool in self.pools:
            if pool.plate_well == well:
                return pool
        return None
    
    def get_sample_xy(self, row: int, col: int) -> Optional[Library | Sample | Pool]:
        return self.get_sample(self.get_well_xy(row, col))
