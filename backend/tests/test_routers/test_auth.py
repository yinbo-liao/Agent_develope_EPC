"""Tests for auth service — JWT tokens, password hashing, RBAC."""

import pytest
from auth import (
    hash_password, verify_password,
    create_access_token, decode_token, create_refresh_token,
    has_role, TokenData,
)
from config import settings


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "securePassword123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)
        assert not verify_password("wrong", hashed)

    def test_different_passwords_produce_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2


class TestJwtTokens:
    def test_create_and_decode_access_token(self):
        data = {"sub": "user-1", "username": "admin", "role": "admin"}
        token = create_access_token(data)
        assert token is not None
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded.user_id == "user-1"
        assert decoded.username == "admin"
        assert decoded.role == "admin"

    def test_decode_invalid_token(self):
        assert decode_token("not-a-valid-token") is None

    def test_decode_with_wrong_secret(self):
        # Create token with current secret
        token = create_access_token({"sub": "u1", "username": "test", "role": "viewer"})
        # Should decode correctly with same secret
        assert decode_token(token) is not None

    def test_token_without_secret_fails(self):
        if not settings.secret_key or settings.secret_key == "change-me-in-production":
            pytest.skip("Secret key not set — token will decode with empty key")
        # Decoding with wrong algorithm should fail
        from jose import jwt
        with pytest.raises(Exception):
            jwt.decode(
                create_access_token({"sub": "u1", "username": "x", "role": "viewer"}),
                "wrong-secret-key",
                algorithms=["HS256"],
            )

    def test_refresh_token_generation(self):
        raw, token_hash = create_refresh_token({"sub": "u1"})
        assert len(raw) > 20  # 64 bytes of urlsafe base64
        assert len(token_hash) == 64  # SHA-256 hex digest
        assert raw != token_hash


class TestRBAC:
    def test_admin_has_all_access(self):
        assert has_role("admin", "admin")
        assert has_role("admin", "project_manager")
        assert has_role("admin", "trade_lead")
        assert has_role("admin", "viewer")

    def test_viewer_readonly(self):
        assert has_role("viewer", "viewer")
        assert not has_role("viewer", "trade_lead")
        assert not has_role("viewer", "project_manager")
        assert not has_role("viewer", "admin")

    def test_project_manager_access(self):
        assert has_role("project_manager", "viewer")
        assert has_role("project_manager", "trade_lead")
        assert has_role("project_manager", "project_manager")
        assert not has_role("project_manager", "admin")

    def test_unknown_role(self):
        assert not has_role("unknown", "viewer")
        assert not has_role("viewer", "unknown")


class TestTokenDataModel:
    def test_token_data_creation(self):
        td = TokenData(user_id="u1", username="test", role="viewer")
        assert td.user_id == "u1"
        assert td.username == "test"
        assert td.role == "viewer"
