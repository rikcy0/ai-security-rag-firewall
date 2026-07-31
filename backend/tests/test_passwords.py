from backend.app.security.passwords import (
    hash_password,
    verify_password
)

def test_hash_password_uses_argon2() -> None:
    password = "temporary-test-password"
    stored_hash = hash_password(password)

    assert stored_hash != password
    assert stored_hash.startswith("$argon2")

def test_verify_password_accepts_correct_password() -> None:
    password = "temporary-test-password"
    stored_hash = hash_password(password)

    assert verify_password(password, stored_hash) is True

def test_verify_password_rejects_incorrect_password() -> None:
    stored_hash = hash_password("correct-password")

    assert verify_password("incorrect-password", stored_hash) is False

def test_hash_password_uses_unique_salts() -> None:
    password = "temporary-test-password"
    first = hash_password(password)
    second = hash_password(password)

    assert first != second
    assert verify_password(password, first) is True
    assert verify_password(password, second) is True

def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("temporary-test-password", "invalid-password-hash") is False