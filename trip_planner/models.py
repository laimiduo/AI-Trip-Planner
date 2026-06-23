"""SQLAlchemy ORM 模型 — TravelPlan / Feedback."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, String, Text, Float, BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trip_planner.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _new_uuid():
    return uuid.uuid4()


class TravelPlan(Base):
    __tablename__ = "travel_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # 用户输入 (反范式化, write-once-read-many)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[str] = mapped_column(String(20), nullable=False)
    end_date: Mapped[str] = mapped_column(String(20), nullable=False)
    travel_days: Mapped[int] = mapped_column(Integer, nullable=False)
    transportation: Mapped[str] = mapped_column(String(100), default="")
    accommodation: Mapped[str] = mapped_column(String(100), default="")
    preferences: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)
    traveler_count: Mapped[int] = mapped_column(Integer, default=1)
    traveler_type: Mapped[str] = mapped_column(String(50), default="solo")
    pace: Mapped[str] = mapped_column(String(50), default="moderate")
    cuisine_preferences: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)
    budget_min: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    budget_max: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    free_text_input: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # 输出
    plan_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)

    # 元信息
    model_name: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    generation_duration_ms: Mapped[Optional[int]] = mapped_column(BigInteger, default=None)

    # 原始 Amap 数据 (可追溯 LLM 输入质量)
    amap_weather_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)
    amap_attraction_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)
    amap_hotel_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)

    # 任务状态
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, default=None)
    task_id: Mapped[Optional[str]] = mapped_column(String(100), default=None, index=True)

    # 关联
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="plan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_travel_plans_created_at", "created_at"),
        Index("idx_travel_plans_city", "city"),
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("travel_plans.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    comment: Mapped[Optional[str]] = mapped_column(Text, default=None)
    category: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    user_session_id: Mapped[Optional[str]] = mapped_column(String(100), default=None)

    plan: Mapped[Optional["TravelPlan"]] = relationship(back_populates="feedbacks")
