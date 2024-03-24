from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from limbless_db.categories import DeliveryStatus, DeliveryStatusEnum

from .Base import Base

if TYPE_CHECKING:
    from .SeqRequest import SeqRequest


class SeqRequestDeliveryContact(Base):
    __tablename__ = "seqrequestdeliverycontact"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=DeliveryStatus.PENDING.id)

    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seqrequest.id"), nullable=False)
    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", back_populates="receiver_contacts")

    @property
    def status(self) -> DeliveryStatusEnum:
        return DeliveryStatus.get(self.status_id)

    def __str__(self) -> str:
        return f"SeqRequestDeliveryLink(email: {self.email})"