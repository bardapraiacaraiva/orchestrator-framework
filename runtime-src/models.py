from datetime import datetime
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str = "dario-orch"
    version: str = "1.0.0"
    uptime_seconds: float
    database: str
    rag_engine: str


class StatusResponse(BaseModel):
    state: str
    autonomy_level: str
    system_health: float
    fitness_score: float
    generation: int
    total_tasks_completed: int
    last_pulse: datetime | None
    started_at: datetime


class TaskStats(BaseModel):
    total: int = 0
    backlog: int = 0
    todo: int = 0
    in_progress: int = 0
    in_review: int = 0
    done: int = 0
    blocked: int = 0


class QualityScoreInput(BaseModel):
    task_id: str | None = None
    skill: str
    project: str | None = None
    specificity: float
    actionability: float
    completeness: float
    accuracy: float
    tone: float
    confidence_mode: str | None = None
    session_id: str | None = None


class FitnessEntry(BaseModel):
    fitness_score: float
    avg_quality: float
    budget_ratio: float
    task_velocity: float
    generation: int
    measured_at: datetime


class HookEvent(BaseModel):
    session_id: str | None = None
    timestamp: str | None = None
    task_id: str | None = None
    skill: str | None = None
    quality_score: float | None = None
    tokens_used: int | None = None


class BudgetAddInput(BaseModel):
    project: str | None = None
    skill: str | None = None
    model: str | None = None
    tokens: int
