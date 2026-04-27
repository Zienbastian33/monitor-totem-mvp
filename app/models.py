from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Totem(Base):
    __tablename__ = "totems"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hostname: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(120), default="")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    screenshots: Mapped[list["Screenshot"]] = relationship(
        back_populates="totem",
        cascade="all, delete-orphan",
        order_by="Screenshot.taken_at.desc()",
    )


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    totem_id: Mapped[int] = mapped_column(ForeignKey("totems.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(500))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    is_archive: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    totem: Mapped[Totem] = relationship(back_populates="screenshots")
