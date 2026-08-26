import logging
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.database import SessionLocal
from backend.app.db.models import SecurityEvent, SecurityEventType, UserRole
from backend.app.security.prompt_injection import PromptInjectionResult


logger = logging.getLogger(__name__)


DEFAULT_SECURITY_EVENT_LIMIT = 50
MAX_SECURITY_EVENT_LIMIT = 100


def _persist_security_event(
    *,
    event_type: SecurityEventType,
    actor_user_id: UUID | None,
    actor_username: str | None,
    details: dict[str, object]
) -> None:
    """
    Persist one event in an isolated database transaction.

    Audit persistence must never change the original security decision.
    Only the exception type is written to the application logger so that
    database details or event data cannot leak through the fallback log.
    """

    try:
        with SessionLocal.begin() as audit_session:
            audit_session.add(
                SecurityEvent(
                    event_type=event_type.value,
                    actor_user_id=actor_user_id,
                    actor_username=actor_username,
                    details=details
                )
            )
    except Exception as exception:
        logger.error(
            "Security event persistence failed: %s",
            type(exception).__name__
        )


def record_failed_login(*, actor_username: str) -> None:
    _persist_security_event(
        event_type=SecurityEventType.LOGIN_FAILED,
        actor_user_id=None,
        actor_username=actor_username,
        details={}
    )


# will be called inside role check defined in access_control.py
# resolves event from the defining module at runtime
def record_authorization_denial(
    *,
    actor_user_id: UUID,
    actor_username: str,
    required_role: UserRole,
    actual_role: str
) -> None:
    _persist_security_event(
        event_type=SecurityEventType.AUTHORIZATION_DENIED,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        details={
            "required_role": required_role.value,
            "actual_role": actual_role
        }
    )


def record_prompt_injection_block(
    *,
    actor_user_id: UUID,
    actor_username: str,
    surface: Literal["document_upload", "rag_query"],
    result: PromptInjectionResult
) -> None:
    _persist_security_event(
        event_type=SecurityEventType.PROMPT_INJECTION_BLOCKED,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        details={
            "surface": surface,
            "risk_score": result.risk_score,
            "matched_categories": sorted(
                category.value for category in result.matched_categories
            )
        }
    )


# listing service (need to be admin role)
def list_security_events(database_session: Session, *, limit: int) -> list[SecurityEvent]:
    if not 1 <= limit <= MAX_SECURITY_EVENT_LIMIT:
        raise ValueError(
            "Security event limit must be between "
            f"1 and {MAX_SECURITY_EVENT_LIMIT}"
        )

    statement = (
        select(SecurityEvent)
        .order_by(
            SecurityEvent.created_at.desc(), # recent items 
            SecurityEvent.id.desc()
        )
        .limit(limit)
    )

    return list(database_session.scalars(statement).all())