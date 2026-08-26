from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.db.models import SecurityEvent, SecurityEventType
from backend.app.schemas.security_events import SecurityEventResponse


def make_security_event() -> SecurityEvent:
    actor_user_id = uuid4()

    event = SecurityEvent(
        event_type=SecurityEventType.AUTHORIZATION_DENIED.value,
        actor_user_id=actor_user_id,
        actor_username="alice",
        details={
            "required_role": "admin",
            "actual_role": "user",
        },
    )

    event.id = uuid4()
    event.created_at = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc,
    )

    return event


def test_security_event_response_accepts_orm_event() -> None:
    event = make_security_event()

    response = SecurityEventResponse.model_validate(event)

    assert response.id == event.id
    assert (
        response.event_type
        is SecurityEventType.AUTHORIZATION_DENIED
    )
    assert response.actor_user_id == event.actor_user_id
    assert response.actor_username == "alice"
    assert response.details == {
        "required_role": "admin",
        "actual_role": "user",
    }
    assert response.created_at == event.created_at


def test_security_event_response_rejects_unknown_event_type() -> None:
    event = make_security_event()
    event.event_type = "authorization_block"

    with pytest.raises(ValidationError):
        SecurityEventResponse.model_validate(event)


def test_security_event_response_rejects_extra_mapping_fields() -> None:
    event = make_security_event()

    with pytest.raises(ValidationError):
        SecurityEventResponse.model_validate(
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor_user_id": event.actor_user_id,
                "actor_username": event.actor_username,
                "details": event.details,
                "created_at": event.created_at,
                "password_hash": "must-not-appear",
            }
        )