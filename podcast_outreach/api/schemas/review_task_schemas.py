import uuid
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class ReviewTaskBase(BaseModel):
    task_type: str = Field(..., description="Type of the review task (e.g., 'match_suggestion', 'pitch_review')")
    related_id: int = Field(..., description="ID of the related entity (e.g., match_id, pitch_gen_id)")
    campaign_id: Optional[uuid.UUID] = None
    assigned_to_id: Optional[int] = Field(None, alias="assigned_to", description="ID of the person assigned to this task")
    status: str = Field(default='pending', description="Current status of the review task")
    notes: Optional[str] = None

class ReviewTaskCreate(ReviewTaskBase):
    pass

class ReviewTaskUpdate(BaseModel):
    status: Optional[str] = Field(None, description="New status for the review task")
    assigned_to_id: Optional[int] = Field(None, alias="assigned_to", description="ID of the person to assign this task to")
    notes: Optional[str] = Field(None, description="Additional notes for the review task update")

class ReviewTaskResponse(ReviewTaskBase):
    review_task_id: int
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

class PaginatedReviewTaskList(BaseModel):
    items: List[ReviewTaskResponse]
    total: int
    page: int
    size: int 