import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.rate_limit import FailureLimiter


def test_production_rejects_insecure_defaults() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", cookie_secure=True)
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="x" * 48, cookie_secure=False)
    ok = Settings(environment="production", jwt_secret="x" * 48, cookie_secure=True)
    assert ok.environment == "production"


def test_cors_origin_list() -> None:
    s = Settings(cors_origins="http://a.test, http://b.test ,")
    assert s.cors_origin_list == ["http://a.test", "http://b.test"]


def test_failure_limiter_blocks_after_threshold_and_resets() -> None:
    limiter = FailureLimiter(max_failures=3, window_seconds=60)
    for _ in range(2):
        limiter.record_failure("k")
    assert not limiter.is_blocked("k")
    limiter.record_failure("k")
    assert limiter.is_blocked("k")
    assert limiter.is_blocked("other", "k")
    limiter.reset("k")
    assert not limiter.is_blocked("k")
