from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue
from backend.app.db.models import SecurityEventType


class SecurityEventResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        allow_inf_nan=False,
        extra="forbid"
    )

    id: UUID
    event_type: SecurityEventType
    actor_user_id: UUID | None
    actor_username: str | None
    details: dict[str, JsonValue] # limits details to JSON-compatible values
    created_at: datetime