from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RiskTier(str, enum.Enum):
    READ_ONLY = "read_only"
    LOW_RISK_WRITE = "low_risk_write"
    HIGH_RISK_DESTRUCTIVE = "high_risk_destructive"
    NETWORK_EGRESS = "network_egress"


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    SNAPSHOTTING = "snapshotting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERTED = "reverted"


class ActionRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"action_{uuid.uuid4().hex[:12]}")
    task_id: str
    subtask_id: str
    action_type: str
    parameters: dict = Field(default_factory=dict)
    risk_tier: RiskTier = RiskTier.READ_ONLY
    status: ActionStatus = ActionStatus.PENDING
    pre_state_hash: Optional[str] = None
    post_state_hash: Optional[str] = None
    diff: Optional[str] = None
    inverse_action: Optional[dict] = None
    container_id: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    reverted_at: Optional[datetime] = None
