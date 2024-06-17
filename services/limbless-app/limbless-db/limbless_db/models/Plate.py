from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Links import LibraryPlateLink
from .Base import Base

if TYPE_CHECKING:
    from .Pool import Pool
    from .User import User
    from .Library import Library


class Plate(Base):
    __tablename__ = "plate"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    num_cols: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    num_rows: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    owner_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", lazy="joined")

    pool_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("pool.id"), nullable=True)
    pool: Mapped[Optional["Pool"]] = relationship(
        "Pool", lazy="select", cascade="save-update, merge"
    )

    library_links: Mapped[list[LibraryPlateLink]] = relationship(
        LibraryPlateLink, back_populates="plate", lazy="select",
        cascade="save-update, merge, delete", order_by="LibraryPlateLink.well"
    )
        
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
    
    def get_library(self, well: str) -> Optional["Library"]:
        for link in self.library_links:
            if link.well == well:
                return link.library
        return None
    
    def get_library_xy(self, row: int, col: int) -> Optional["Library"]:
        return self.get_library(self.get_well_xy(row, col))

    def get_next_available_well(self) -> Optional[str]:
        for i in range(self.num_cols * self.num_rows):
            well = self.get_well(i)
            if self.get_library(well) is None:
                return well
        return None
