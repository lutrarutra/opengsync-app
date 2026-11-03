import re
from typing import TYPE_CHECKING, ClassVar, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .Sample import Sample
    from .Library import Library
    from .Pool import Pool


DeliverableKind = Literal["sample", "library", "pool"]


class SampleSubmissionLayout(Base):
    """Where one sample, library or pool of a request sits when it is handed in: a well of a plate or a labelled tube of a set."""
    __tablename__ = "sample_submission_layout"

    PLATE_NUM_ROWS: ClassVar[int] = 8
    PLATE_NUM_COLS: ClassVar[int] = 12
    MAX_SET_NAME_LENGTH: ClassVar[int] = 64
    MAX_POSITION_LENGTH: ClassVar[int] = 32

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)

    seq_request_id: Mapped[int] = mapped_column(sa.ForeignKey("seq_request.id", ondelete="CASCADE"), nullable=False, index=True)
    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", back_populates="submission_layout", lazy="select")

    sample_id: Mapped[int | None] = mapped_column(sa.ForeignKey("sample.id", ondelete="CASCADE"), nullable=True)
    sample: Mapped["Sample | None"] = relationship("Sample", lazy="select")
    library_id: Mapped[int | None] = mapped_column(sa.ForeignKey("library.id", ondelete="CASCADE"), nullable=True)
    library: Mapped["Library | None"] = relationship("Library", lazy="select")
    pool_id: Mapped[int | None] = mapped_column(sa.ForeignKey("pool.id", ondelete="CASCADE"), nullable=True)
    pool: Mapped["Pool | None"] = relationship("Pool", lazy="select")

    set_name: Mapped[str] = mapped_column(sa.String(MAX_SET_NAME_LENGTH), nullable=False, default="", server_default="")
    """Plate name or tube set; '' is the default plate/set."""
    position: Mapped[str] = mapped_column(sa.String(MAX_POSITION_LENGTH), nullable=False)
    """Well (normalised, e.g. 'A1') or tube label."""

    __table_args__ = (
        sa.CheckConstraint(
            "(sample_id IS NOT NULL)::int + (library_id IS NOT NULL)::int + (pool_id IS NOT NULL)::int = 1",
            name="ck_sample_submission_layout_one_item",
        ),
        sa.UniqueConstraint("seq_request_id", "set_name", "position", name="uq_sample_submission_layout_position"),
    )

    @property
    def kind(self) -> DeliverableKind:
        if self.sample_id is not None:
            return "sample"
        if self.library_id is not None:
            return "library"
        return "pool"

    @property
    def item(self) -> "Sample | Library | Pool":
        item = self.sample or self.library or self.pool
        if item is None:
            raise ValueError(f"{self} has neither a sample, library nor pool")
        return item

    @property
    def item_name(self) -> str:
        return self.item.name

    @property
    def well_xy(self) -> tuple[int, int]:
        """(row, col) of the well; only meaningful for plate layouts."""
        return SampleSubmissionLayout.well_to_xy(self.position)

    @staticmethod
    def normalize_well(well: str, num_rows: int = PLATE_NUM_ROWS, num_cols: int = PLATE_NUM_COLS) -> str:
        """'a01 ' -> 'A1'. Raises ValueError if the well is not on the plate."""
        if (match := re.fullmatch(r"([A-Z])0*([1-9]\d*)", well.strip().upper())) is None:
            raise ValueError(f"Invalid well '{well}'")
        row, col = ord(match.group(1)) - ord("A"), int(match.group(2)) - 1
        if row >= num_rows or col >= num_cols:
            raise ValueError(f"Invalid well '{well}'")
        return f"{match.group(1)}{col + 1}"

    @staticmethod
    def well_to_xy(well: str) -> tuple[int, int]:
        well = SampleSubmissionLayout.normalize_well(well)
        return ord(well[0]) - ord("A"), int(well[1:]) - 1

    def __str__(self) -> str:
        return f"SampleSubmissionLayout(seq_request_id: {self.seq_request_id}, {self.kind}: {self.sample_id or self.library_id or self.pool_id}, set_name: '{self.set_name}', position: '{self.position}')"

    def __repr__(self) -> str:
        return self.__str__()
