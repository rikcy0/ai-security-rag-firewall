from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest.mock import Mock, call
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from backend.app.db.database import SessionLocal
from backend.app.db.models import (
    Document,
    DocumentChunk,
    SecurityEvent,
    SecurityEventType,
    User
)
from backend.app.main import app
from backend.app.rag.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingProvider,
)
from backend.app.rag.generator import (
    AnswerContext,
    AnswerProvider,
    GeneratedAnswer,
)
from backend.app.routes import dependencies as route_dependencies
from backend.app.routes import document_routes, rag_routes
from backend.app.schemas.security_events import SecurityEventResponse
from backend.app.security.prompt_injection import PromptInjectionCategory
from backend.app.services import documents as document_service
from backend.app.services import rag as rag_service
from backend.tests.adversarial.constants import DETECTOR_EVALUATION_THRESHOLD
from backend.tests.adversarial.corpus import AdversarialCase, load_corpus


pytestmark = pytest.mark.integration

TEST_PASSWORD = "adversarial-integration-password"

MALICIOUS_CORPUS = load_corpus(
    Path(__file__).parent
    / "cases"
    / "malicious_prompts.json"
)

CASES_BY_ID = {
    case.id: case
    for case in MALICIOUS_CORPUS.cases
}

BENIGN_CORPUS = load_corpus(
    Path(__file__).parent
    / "cases"
    / "benign_prompts.json"
)

BENIGN_CASES_BY_ID = {
    case.id: case
    for case in BENIGN_CORPUS.cases
}

RAG_BLOCKED_CASES = tuple(
    CASES_BY_ID[case_id]
    for case_id in (
        "override-direct-001",
        "override-zero-width-boundary-001",
        "multi-category-001",
    )
)


UPLOAD_BLOCKED_CASES = tuple(
    CASES_BY_ID[case_id]
    for case_id in (
        "override-direct-001",
        "indirect-html-comment-001",
        "long-prefix-001",
    )
)


@pytest.fixture
def adversarial_username() -> Iterator[str]:
    username = f"adv-user-{uuid4().hex}"

    try:
        yield username
    finally:
        with SessionLocal() as database_session:
            database_session.execute(
                delete(SecurityEvent).where(
                    SecurityEvent.actor_username == username
                )
            )
            database_session.execute(
                delete(User).where(
                    User.username == username
                )
            )
            database_session.commit()


@pytest.fixture
def adversarial_providers(monkeypatch) -> tuple[Mock, Mock]:
    embedding_provider = Mock(spec=EmbeddingProvider)
    answer_provider = Mock(spec=AnswerProvider)

    embedding_provider.embed_texts.side_effect = AssertionError(
        "A blocked request must not reach the embedding provider"
    )
    answer_provider.generate_answer.side_effect = AssertionError(
        "A blocked request must not reach the answer provider"
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        route_dependencies.get_embedding_provider,
        lambda: embedding_provider,
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        route_dependencies.get_answer_provider,
        lambda: answer_provider,
    )

    return embedding_provider, answer_provider


@pytest.fixture
def adversarial_rag_settings(monkeypatch) -> None:
    settings = SimpleNamespace(
        rag_answer_top_k=5,
        rag_max_context_characters=20_000,
        prompt_injection_block_threshold=(
            DETECTOR_EVALUATION_THRESHOLD
        ),
    )

    monkeypatch.setattr(
        rag_routes,
        "get_settings",
        lambda: settings,
    )


@pytest.fixture
def adversarial_document_settings(monkeypatch) -> None:
    settings = SimpleNamespace(
        max_upload_size_bytes=4_096,
        chunk_size_characters=100,
        chunk_overlap_characters=20,
        prompt_injection_block_threshold=(
            DETECTOR_EVALUATION_THRESHOLD
        ),
    )

    monkeypatch.setattr(
        document_routes,
        "get_settings",
        lambda: settings,
    )


def register_and_login(client: TestClient, username: str) -> tuple[UUID, str]:
    registration = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": TEST_PASSWORD,
        },
    )

    assert registration.status_code == 201

    login = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": TEST_PASSWORD,
        },
    )

    assert login.status_code == 200

    return (
        UUID(registration.json()["id"]),
        login.json()["access_token"],
    )


def assert_safe_block_event(
    *,
    username: str,
    user_id: UUID,
    access_token: str,
    case: AdversarialCase,
    surface: Literal["rag_query", "document_upload"],
) -> None:
    with SessionLocal() as database_session:
        events = list(
            database_session.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.actor_username == username
                )
            ).all()
        )

        assert len(events) == 1

        event = events[0]

        assert event.event_type == (
            SecurityEventType.PROMPT_INJECTION_BLOCKED.value
        )
        assert event.actor_user_id == user_id
        assert event.actor_username == username
        assert event.created_at is not None

        assert set(event.details) == {
            "surface",
            "risk_score",
            "matched_categories",
        }
        assert event.details["surface"] == surface

        risk_score = event.details["risk_score"]

        assert type(risk_score) is int
        assert (
            DETECTOR_EVALUATION_THRESHOLD
            <= risk_score
            <= 100
        )

        matched_categories = event.details["matched_categories"]

        assert isinstance(matched_categories, list)
        assert matched_categories == sorted(
            set(matched_categories)
        )

        assert set(matched_categories).issubset(
            {
                category.value
                for category in PromptInjectionCategory
            }
        )
        assert {
            category.value
            for category in case.required_detected_categories
        }.issubset(matched_categories)

        serialized_event = (
            SecurityEventResponse.model_validate(event)
            .model_dump_json()
        )

    assert case.text not in serialized_event
    assert access_token not in serialized_event
    assert TEST_PASSWORD not in serialized_event
    assert "password_hash" not in serialized_event


@pytest.mark.parametrize(
    "case",
    RAG_BLOCKED_CASES,
    ids=lambda case: case.id,
)
def test_blocked_rag_case_stops_downstream_work_and_records_safe_event(
    case: AdversarialCase,
    client: TestClient,
    adversarial_username: str,
    adversarial_providers: tuple[Mock, Mock],
    adversarial_rag_settings: None,
    monkeypatch
) -> None:
    embedding_provider, answer_provider = adversarial_providers

    retrieval_guard = Mock(
        side_effect=AssertionError(
            "A blocked query must not enter retrieval"
        )
    )

    # Patch the name where the RAG service looks it up.
    monkeypatch.setattr(
        rag_service,
        "retrieve_chunks_for_owner",
        retrieval_guard,
    )

    user_id, access_token = register_and_login(
        client,
        adversarial_username,
    )

    response = client.post(
        "/rag/answer",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        json={
            "query": case.text,
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Query rejected by security policy"
    }

    retrieval_guard.assert_not_called()
    embedding_provider.embed_texts.assert_not_called()
    answer_provider.generate_answer.assert_not_called()

    assert_safe_block_event(
        username=adversarial_username,
        user_id=user_id,
        access_token=access_token,
        case=case,
        surface="rag_query",
    )


@pytest.mark.parametrize(
    "case",
    UPLOAD_BLOCKED_CASES,
    ids=lambda case: case.id,
)
def test_blocked_upload_stops_processing_and_persists_only_safe_event(
    case: AdversarialCase,
    client: TestClient,
    adversarial_username: str,
    adversarial_providers: tuple[Mock, Mock],
    adversarial_document_settings: None,
    monkeypatch
) -> None:
    embedding_provider, answer_provider = adversarial_providers

    chunking_guard = Mock(
        side_effect=AssertionError(
            "A blocked upload must not enter chunking"
        )
    )

    # The document service looks up chunk_text in this module.
    monkeypatch.setattr(
        document_service,
        "chunk_text",
        chunking_guard,
    )

    user_id, access_token = register_and_login(
        client,
        adversarial_username,
    )

    response = client.post(
        "/documents",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        files={
            "file": (
                "adversarial-notes.md",
                case.text.encode("utf-8"),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Document rejected by prompt-injection policy"
    }

    chunking_guard.assert_not_called()
    embedding_provider.embed_texts.assert_not_called()
    answer_provider.generate_answer.assert_not_called()

    with SessionLocal() as database_session:
        document_count = database_session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.owner_id == user_id)
        )

        chunk_count = database_session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .join(
                Document,
                DocumentChunk.document_id == Document.id,
            )
            .where(Document.owner_id == user_id)
        )

    assert document_count == 0
    assert chunk_count == 0

    assert_safe_block_event(
        username=adversarial_username,
        user_id=user_id,
        access_token=access_token,
        case=case,
        surface="document_upload",
    )


def test_benign_security_document_can_be_uploaded_and_used_for_an_answer(
    client: TestClient,
    adversarial_username: str,
    adversarial_providers: tuple[Mock, Mock],
    adversarial_document_settings: None,
    adversarial_rag_settings: None,
) -> None:
    embedding_provider, answer_provider = adversarial_providers

    case = BENIGN_CASES_BY_ID[
        "benign-bypass-definition-001"
    ]
    document_text = case.text
    query = "How does the document define a security bypass?"
    expected_answer = (
        "A security bypass is a vulnerability "
        "that attackers may attempt [1]."
    )

    # A valid nonzero unit vector. Document and query use the
    # same vector so this test has deterministic similarity.
    expected_embedding = [
        1.0,
        *([0.0] * (EMBEDDING_DIMENSIONS - 1)),
    ]

    def embed_expected_texts(
        texts: list[str],
    ) -> list[list[float]]:
        assert texts in (
            [document_text],
            [query],
        ), "Unexpected input reached the embedding provider"

        return [expected_embedding.copy()]

    # Replace the blocked-request guards for this test only.
    # Pytest creates fresh provider mocks for every test case.
    embedding_provider.embed_texts.side_effect = (
        embed_expected_texts
    )

    answer_provider.generate_answer.side_effect = None
    answer_provider.generate_answer.return_value = GeneratedAnswer(
        status="answered",
        answer=expected_answer,
        cited_source_numbers=[1],
    )

    user_id, access_token = register_and_login(
        client,
        adversarial_username,
    )

    authorization_headers = {
        "Authorization": f"Bearer {access_token}"
    }

    upload_response = client.post(
        "/documents",
        headers=authorization_headers,
        files={
            "file": (
                "benign-security-definition.md",
                document_text.encode("utf-8"),
                "text/markdown",
            )
        },
    )

    assert upload_response.status_code == 201

    document_id = UUID(upload_response.json()["id"])

    with SessionLocal() as database_session:
        stored_document = database_session.get(
            Document,
            document_id,
        )

        assert stored_document is not None
        assert stored_document.owner_id == user_id
        assert stored_document.content == document_text

        stored_chunks = list(
            database_session.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == document_id
                )
                .order_by(DocumentChunk.chunk_index)
            ).all()
        )

        # This corpus entry fits within the configured
        # 100-character chunk size.
        assert len(stored_chunks) == 1

        stored_chunk = stored_chunks[0]

        assert stored_chunk.chunk_index == 0
        assert stored_chunk.content == document_text
        assert list(stored_chunk.embedding) == pytest.approx(
            expected_embedding
        )

        chunk_id = stored_chunk.id

    answer_response = client.post(
        "/rag/answer",
        headers=authorization_headers,
        json={
            "query": query,
        },
    )

    assert answer_response.status_code == 200

    response_data = answer_response.json()

    assert response_data["status"] == "answered"
    assert response_data["answer"] == expected_answer
    assert len(response_data["sources"]) == 1

    source = response_data["sources"][0]

    assert set(source) == {
        "source_number",
        "chunk_id",
        "document_id",
        "filename",
        "chunk_index",
        "similarity",
    }
    assert source["source_number"] == 1
    assert source["chunk_id"] == str(chunk_id)
    assert source["document_id"] == str(document_id)
    assert source["filename"] == "benign-security-definition.md"
    assert source["chunk_index"] == 0
    assert source["similarity"] == pytest.approx(1.0)

    # Exactly two embedding calls, in workflow order:
    # document ingestion, then query retrieval.
    assert embedding_provider.embed_texts.call_args_list == [
        call([document_text]),
        call([query]),
    ]

    answer_provider.generate_answer.assert_called_once_with(
        query,
        [
            AnswerContext(
                source_number=1,
                content=document_text,
            )
        ],
    )

    with SessionLocal() as database_session:
        event_count = database_session.scalar(
            select(func.count())
            .select_from(SecurityEvent)
            .where(
                SecurityEvent.actor_username
                == adversarial_username
            )
        )

    assert event_count == 0
