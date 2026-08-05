from sqlalchemy import CheckConstraint, UniqueConstraint

from backend.app.db.models import User, UserRole


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