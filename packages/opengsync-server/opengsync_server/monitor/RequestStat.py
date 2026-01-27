from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import timezone


class MonitorBase(DeclarativeBase):
    pass

class RequestStat(MonitorBase):
    __tablename__ = "request_stat"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    method: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    requestor_ip: Mapped[str | None] = mapped_column(sa.String(45), nullable=True)
    response_status: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


