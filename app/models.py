from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    company: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(30), default="lead", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deals: Mapped[list["Deal"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
        order_by="Deal.created_at.desc()",
    )


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    stage: Mapped[str] = mapped_column(String(30), default="new", index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    client: Mapped[Client] = relationship(back_populates="deals")
