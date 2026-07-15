from pydantic import BaseModel
from typing import Literal
from datetime import datetime

class SyncEvent(BaseModel):
    id: str
    timestamp: datetime
    source_model: Literal["claude", "gpt"]
    target_model: Literal["claude", "gpt"]
    project_tag: str
    content_type: Literal["message", "file", "code", "system_prompt"]
    content: str
    synthesized_code: str
    requires_approval: bool
    status: Literal["pending", "approved", "rejected", "synced"]
    embedding: list[float] | None = None
