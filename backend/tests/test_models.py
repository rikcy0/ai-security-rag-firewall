from sqlalchemy import CheckConstraint, UniqueConstraint
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects.postgresql import JSONB

from backend.app.db.models import (
    Document, DocumentChunk, User, UserRole,
    SecurityEvent, SecurityEventType)
from backend.app.rag.embeddings import EMBEDDING_DIMENSIONS

def test_user_model_has_only_expected_columns() -> None:
    column_names = set(User.__table__.columns.keys())

    assert column_names == {
        "id",
        "username",
        "password_hash",
        "role",
        "is_active",
        "created_at",
    }
    assert "password" not in column_names


def test_username_is_required_and_unique() -> None:
    username_column = User.__table__.columns["username"]

    unique_constraints = [
        constraint
        for constraint in User.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert username_column.nullable is False
    assert any(
        tuple(constraint.columns.keys()) == ("username",)
        for constraint in unique_constraints
    )


def test_user_role_values_are_limited() -> None:
    assert {role.value for role in UserRole} == {"user", "admin"}


def test_user_role_is_required_and_defaults_to_user() -> None:
    role_column = User.__table__.columns["role"]

    assert role_column.nullable is False
    assert role_column.type.length == 20
    assert role_column.default is not None
    assert role_column.server_default is not None
    assert str(role_column.default.arg) == UserRole.USER.value
    assert str(role_column.server_default.arg) == UserRole.USER.value


def test_database_constrains_user_roles() -> None:
    role_constraints = [
        constraint
        for constraint in User.__table__.constraints
        if (
            isinstance(constraint, CheckConstraint)
            and constraint.name == "ck_users_role"
        )
    ]

    assert len(role_constraints) == 1

    constraint_sql = str(role_constraints[0].sqltext)

    assert "'user'" in constraint_sql
    assert "'admin'" in constraint_sql


def test_document_model_has_expected_columns() -> None:
    column_names = set(Document.__table__.columns.keys())

    assert column_names == {
        "id",
        "owner_id",
        "filename",
        "content_type",
        "size_bytes",
        "content",
        "created_at",
    }


def test_document_owner_is_required_indexed_and_cascades() -> None:
    owner_column = Document.__table__.columns["owner_id"]

    assert owner_column.nullable is False
    assert owner_column.index is True

    foreign_keys = list(owner_column.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "users.id"
    assert foreign_keys[0].ondelete == "CASCADE"


def test_document_has_content_and_size_constraints() -> None:
    constraint_names = {
        constraint.name
        for constraint in Document.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_documents_size_bytes_positive" in constraint_names
    assert "ck_documents_content_not_empty" in constraint_names


def test_document_chunk_model_has_expected_columns() -> None:
    column_names = set(DocumentChunk.__table__.columns.keys())

    assert column_names == {
        "id",
        "document_id",
        "chunk_index",
        "content",
        "embedding"
    }


def test_document_chunks_have_parent_and_ordering_constraints() -> None:
    document_id_column = DocumentChunk.__table__.columns[
        "document_id"
    ]

    assert document_id_column.nullable is False
    assert document_id_column.index is True

    foreign_keys = list(document_id_column.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "documents.id"
    assert foreign_keys[0].ondelete == "CASCADE"

    unique_constraints = [
        constraint
        for constraint in DocumentChunk.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        (
            constraint.name == "uq_document_chunks_document_id_chunk_index"
            and 
            tuple(constraint.columns.keys()) == ("document_id", "chunk_index")
        )
        for constraint in unique_constraints
    )

    check_constraint_names = {
        constraint.name
        for constraint in DocumentChunk.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert ("ck_document_chunks_chunk_index_nonnegative" in check_constraint_names)
    assert ("ck_document_chunks_content_not_empty" in check_constraint_names)


def test_document_chunk_embedding_is_required_and_fixed_dimension() -> None:
    embedding_column = DocumentChunk.__table__.columns["embedding"]

    assert embedding_column.nullable is False
    assert isinstance(embedding_column.type, VECTOR)
    assert embedding_column.type.dim == EMBEDDING_DIMENSIONS


def test_document_chunk_has_hnsw_cosine_index() -> None:
    embedding_index = next(
        index
        for index in DocumentChunk.__table__.indexes
        if index.name == "ix_document_chunks_embedding_hnsw"
    )

    assert tuple(column.name for column in embedding_index.columns) == ("embedding",)

    postgresql_options = embedding_index.dialect_options["postgresql"]

    assert postgresql_options["using"] == "hnsw"
    assert postgresql_options["ops"] == {"embedding": "vector_cosine_ops"}


def test_security_event_type_values_are_closed() -> None:
    assert {
        event_type.value
        for event_type in SecurityEventType
    } == {
        "login_failed",
        "authorization_denied",
        "prompt_injection_blocked",
    }


def test_security_event_model_has_expected_columns() -> None:
    assert set(SecurityEvent.__table__.columns.keys()) == {
        "id",
        "event_type",
        "actor_user_id",
        "actor_username",
        "details",
        "created_at",
    }


def test_security_event_actor_is_optional_and_survives_user_deletion() -> None:
    actor_column = SecurityEvent.__table__.columns[
        "actor_user_id"
    ]

    assert actor_column.nullable is True

    foreign_keys = list(actor_column.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "users.id"
    assert foreign_keys[0].ondelete == "SET NULL"


def test_security_event_details_are_required_jsonb_objects() -> None:
    details_column = SecurityEvent.__table__.columns[
        "details"
    ]

    assert isinstance(details_column.type, JSONB)
    assert details_column.nullable is False
    assert details_column.default is not None
    assert details_column.server_default is not None

    constraint_names = {
        constraint.name
        for constraint in SecurityEvent.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_security_events_event_type" in constraint_names
    assert "ck_security_events_details_object" in constraint_names


def test_security_event_has_deterministic_ordering_index() -> None:
    ordering_index = next(
        index
        for index in SecurityEvent.__table__.indexes
        if index.name == "ix_security_events_created_at_id"
    )

    assert tuple(
        column.name
        for column in ordering_index.columns
    ) == (
        "created_at",
        "id",
    )