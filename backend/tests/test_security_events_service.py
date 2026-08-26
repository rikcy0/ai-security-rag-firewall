from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql

from backend.app.db.models import SecurityEvent, SecurityEventType, UserRole
from backend.app.security.prompt_injection import PromptInjectionCategory, PromptInjectionDecision, PromptInjectionResult
from backend.app.services import security_events


@pytest.fixture
def isolated_audit_session(monkeypatch) -> tuple[Mock, Mock, MagicMock]:
    audit_session = Mock(spec=Session)

    transaction_context = MagicMock()
    transaction_context.__enter__.return_value = audit_session
    transaction_context.__exit__.return_value = False

    session_factory = Mock()
    session_factory.begin.return_value = transaction_context

    monkeypatch.setattr(
        security_events,
        "SessionLocal",
        session_factory,
    )

    return (
        audit_session,
        session_factory,
        transaction_context,
    )


def get_added_event(audit_session: Mock) -> SecurityEvent:
    event = audit_session.add.call_args.args[0]

    assert isinstance(event, SecurityEvent)

    return event


def test_record_failed_login_uses_submitted_username_without_user_id(
    isolated_audit_session: tuple[Mock, Mock, MagicMock],
) -> None:
    audit_session, session_factory, _ = isolated_audit_session

    security_events.record_failed_login(
        actor_username="alice",
    )

    event = get_added_event(audit_session)

    assert event.event_type == SecurityEventType.LOGIN_FAILED.value
    assert event.actor_user_id is None
    assert event.actor_username == "alice"
    assert event.details == {}

    session_factory.begin.assert_called_once_with()


def test_record_authorization_denial_stores_role_evidence(
    isolated_audit_session: tuple[Mock, Mock, MagicMock],
) -> None:
    audit_session, _, _ = isolated_audit_session
    actor_user_id = uuid4()

    security_events.record_authorization_denial(
        actor_user_id=actor_user_id,
        actor_username="alice",
        required_role=UserRole.ADMIN,
        actual_role=UserRole.USER.value,
    )

    event = get_added_event(audit_session)

    assert (
        event.event_type
        == SecurityEventType.AUTHORIZATION_DENIED.value
    )
    assert event.actor_user_id == actor_user_id
    assert event.actor_username == "alice"
    assert event.details == {
        "required_role": "admin",
        "actual_role": "user",
    }


def test_record_prompt_injection_block_stores_only_derived_evidence(
    isolated_audit_session: tuple[Mock, Mock, MagicMock],
) -> None:
    audit_session, _, _ = isolated_audit_session
    actor_user_id = uuid4()

    result = PromptInjectionResult(
        decision=PromptInjectionDecision.BLOCK,
        risk_score=100,
        matched_categories=(
            PromptInjectionCategory.INSTRUCTION_OVERRIDE,
            PromptInjectionCategory.DATA_EXFILTRATION,
        ),
        reasons=(
            "private instruction reason",
            "private exfiltration reason",
        ),
    )

    security_events.record_prompt_injection_block(
        actor_user_id=actor_user_id,
        actor_username="alice",
        surface="rag_query",
        result=result,
    )

    event = get_added_event(audit_session)

    assert (
        event.event_type
        == SecurityEventType.PROMPT_INJECTION_BLOCKED.value
    )
    assert event.actor_user_id == actor_user_id
    assert event.actor_username == "alice"
    assert event.details == {
        "surface": "rag_query",
        "risk_score": 100,
        "matched_categories": [
            "data_exfiltration",
            "instruction_override"
        ],
    }

    serialized_details = repr(event.details)

    assert "private instruction reason" not in serialized_details
    assert "private exfiltration reason" not in serialized_details


def test_audit_persistence_failure_is_safely_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_error = "private database connection details"

    session_factory = Mock()
    session_factory.begin.side_effect = RuntimeError(
        private_error
    )

    fallback_logger = Mock()

    monkeypatch.setattr(
        security_events,
        "SessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        security_events,
        "logger",
        fallback_logger,
    )

    security_events.record_failed_login(
        actor_username="alice",
    )

    fallback_logger.error.assert_called_once_with(
        "Security event persistence failed: %s",
        "RuntimeError",
    )

    assert private_error not in repr(
        fallback_logger.error.call_args
    )


def test_list_security_events_is_bounded_and_newest_first() -> None:
    database_session = Mock(spec=Session)

    first_event = SecurityEvent(
        event_type=SecurityEventType.LOGIN_FAILED.value,
        actor_user_id=None,
        actor_username="first-user",
        details={},
    )
    second_event = SecurityEvent(
        event_type=SecurityEventType.LOGIN_FAILED.value,
        actor_user_id=None,
        actor_username="second-user",
        details={},
    )

    database_session.scalars.return_value.all.return_value = [
        first_event,
        second_event,
    ]

    result = security_events.list_security_events(
        database_session,
        limit=2,
    )

    assert result == [
        first_event,
        second_event,
    ]

    statement = database_session.scalars.call_args.args[0]

    compiled_statement = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    )

    assert (
        "ORDER BY security_events.created_at DESC, "
        "security_events.id DESC"
        in compiled_statement
    )
    assert "LIMIT 2" in compiled_statement


@pytest.mark.parametrize(
    "invalid_limit",
    [
        0,
        security_events.MAX_SECURITY_EVENT_LIMIT + 1,
    ],
)
def test_list_security_events_rejects_invalid_limit(invalid_limit: int) -> None:
    database_session = Mock(spec=Session)

    with pytest.raises(
        ValueError,
        match="must be between",
    ):
        security_events.list_security_events(
            database_session,
            limit=invalid_limit,
        )

    database_session.scalars.assert_not_called()