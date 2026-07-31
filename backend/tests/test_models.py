from sqlalchemy import UniqueConstraint

from backend.app.db.models import User


def test_user_model_has_only_expected_columns() -> None:
    column_names = set(User.__table__.columns.keys())

    assert column_names == {
        "id",
        "username",
        "password_hash",
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