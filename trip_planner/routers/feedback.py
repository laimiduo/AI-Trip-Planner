"""用户反馈路由 — 需要 PostgreSQL."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trip_planner.dependencies import get_db_session
from trip_planner.models import Feedback

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    plan_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    category: Optional[str] = None
    user_session_id: Optional[str] = None


class FeedbackResponse(BaseModel):
    success: bool
    message: str = ""
    id: Optional[str] = None


@router.post("", response_model=FeedbackResponse)
async def create_feedback(data: FeedbackCreate, db: AsyncSession = Depends(get_db_session)):
    """提交用户反馈."""
    import uuid
    record = Feedback(
        rating=data.rating,
        comment=data.comment,
        category=data.category,
        user_session_id=data.user_session_id,
    )
    if data.plan_id:
        try:
            record.plan_id = uuid.UUID(data.plan_id)
        except ValueError:
            pass
    db.add(record)
    await db.commit()
    return FeedbackResponse(success=True, message="感谢反馈！", id=str(record.id))


@router.get("")
async def list_feedback(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """查看反馈列表."""
    result = await db.execute(select(Feedback).order_by(Feedback.created_at.desc()).limit(limit))
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "rating": r.rating,
            "comment": r.comment,
            "category": r.category,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]
