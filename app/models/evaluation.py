import uuid
from datetime import datetime, timezone
from typing import Optional, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, JSON, Enum as SQLEnum

from app.models.enums import ScreeningStrategy

if TYPE_CHECKING:
    from app.models.candidate import Candidate


class CandidateEvaluation(SQLModel, table=True):
    __tablename__ = "candidate_evaluations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    candidate_id: uuid.UUID = Field(foreign_key="candidates.id", unique=True, index=True, nullable=False)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id", index=True, nullable=False)
    
    screening_strategy: ScreeningStrategy = Field(
        sa_column=Column(SQLEnum(ScreeningStrategy), nullable=False, default=ScreeningStrategy.HYBRID)
    )
    
    overall_match_score: float = Field(default=0.0, nullable=False)
    skill_match_score: float = Field(default=0.0, nullable=False)
    semantic_score: float = Field(default=0.0, nullable=False)
    experience_score: float = Field(default=0.0, nullable=False)
    portfolio_score: float = Field(default=0.0, nullable=False)
    
    rank: Optional[int] = Field(default=None)
    is_shortlisted: bool = Field(default=False, nullable=False)
    
    key_strengths: Any = Field(default_factory=list, sa_column=Column(JSON))
    potential_concerns: Any = Field(default_factory=list, sa_column=Column(JSON))
    summary_reasoning: str = Field(nullable=False)
    
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    candidate: Optional["Candidate"] = Relationship(back_populates="evaluation")
