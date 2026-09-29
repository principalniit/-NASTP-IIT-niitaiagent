import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("a-long-password-123")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "a-long-password-123")
    assert not verify_password(hashed, "wrong-password-123")
    assert not verify_password(None, "anything")
    assert not verify_password("not-a-hash", "anything")


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token, ttl = create_access_token(user_id)
    assert ttl == get_settings().access_token_ttl_minutes * 60
    assert decode_access_token(token) == user_id


def _token(**overrides: object) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "jti": "x",
        "typ": "access",
    }
    claims.update(overrides)
    secret = str(claims.pop("_secret", s.jwt_secret.get_secret_value()))
    alg = str(claims.pop("_alg", "HS256"))
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, secret, algorithm=alg)


def test_rejects_invalid_tokens() -> None:
    assert decode_access_token(_token()) is not None
    assert decode_access_token(_token(exp=datetime.now(UTC) - timedelta(seconds=1))) is None
    assert decode_access_token(_token(aud="someone-else")) is None
    assert decode_access_token(_token(iss="someone-else")) is None
    assert decode_access_token(_token(typ="refresh")) is None
    assert decode_access_token(_token(jti=None)) is None
    assert decode_access_token(_token(sub="not-a-uuid")) is None
    assert decode_access_token(_token(_secret="another-secret-that-is-long-enough")) is None
    assert decode_access_token("garbage") is None
    unsigned = jwt.encode({"sub": str(uuid.uuid4())}, key=None, algorithm="none")  # type: ignore[arg-type]
    assert decode_access_token(unsigned) is None


def test_refresh_token_hash_is_stable_and_not_plaintext() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != "abc"
    assert len(hash_token("abc")) == 64
