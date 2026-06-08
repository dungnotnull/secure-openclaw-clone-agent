from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InverseActionType(str, enum.Enum):
    FILE_RESTORE = "file_restore"
    UNDO_SCRIPT = "undo_script"
    COMPENSATING_API = "compensating_api"
    MANUAL_REQUIRED = "manual_required"


class InverseActionDescriptor(BaseModel):
    action_type: InverseActionType
    description: str
    payload: dict = Field(default_factory=dict)


class LedgerEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"ledger_{uuid.uuid4().hex[:12]}")
    action_id: str
    task_id: str
    action_type: str
    pre_state_hash: str
    post_state_hash: Optional[str] = None
    diff: Optional[str] = None
    inverse_action: InverseActionDescriptor
    hmac_signature: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reverted: bool = False
    reverted_at: Optional[datetime] = None
