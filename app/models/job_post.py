import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, Enum as SQLEnum

from app.models.enums import PlatformType

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class JobPost(SQLModel, table=True):
    __tablename__ = "job_posts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id", index=True, nullable=False)
    
    platform: PlatformType = Field(
        sa_column=Column(SQLEnum(PlatformType), nullable=False, default=PlatformType.GENERIC_WEB)
    )
    title: str = Field(nullable=False)
    content: str = Field(nullable=False)
    
    is_published: bool = Field(default=False, nullable=False)
    published_at: Optional[datetime] = Field(default=None)
    repost_count: int = Field(default=0, nullable=False)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign: Optional["Campaign"] = Relationship(back_populates="job_posts")
