"""Supabase JWT auth: real verification path (no dependency override).

A throwaway ES256 keypair stands in for Supabase's signing key; the JWKS fetch
is mocked so no network is touched.
"""
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.security import HTTPAuthorizationCredentials
from jwt.algorithms import ECAlgorithm

from middleware import auth

ISSUER = "https://test-project.supabase.co/auth/v1"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
AUDIENCE = "authenticated"
KID = "test-key-1"

PROTECTED = [
    ("get", "/api/cases"),
    ("get", "/api/cases/1"),
    ("patch", "/api/cases/1"),
    ("post", "/api/cases/1/analyze"),
    ("get", "/api/sectors"),
    ("get", "/api/units"),
    ("get", "/api/config"),
    ("get", "/api/robots"),
]


def _call(c, method, path, token=None, scheme="Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    kwargs = {"json": {"notes": "checked by test"}} if method == "patch" else {}
    return getattr(c, method)(path, headers=headers, **kwargs)


@pytest.fixture
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def jwks_calls(monkeypatch, signing_key):
    """Point auth at test config and serve the test key from a mocked JWKS fetch."""
    monkeypatch.setenv("AUTH_ISSUER_URL", ISSUER)
    monkeypatch.setenv("AUTH_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("AUTH_AUDIENCE", AUDIENCE)
    jwk = ECAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    jwk.update(kid=KID, alg="ES256", use="sig")
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return {"keys": [jwk]}

    monkeypatch.setattr(auth, "fetch_jwks", fake_fetch)
    auth.jwks_cache.clear()
    yield calls
    auth.jwks_cache.clear()


@pytest.fixture
def make_token(signing_key):
    def make(key=None, kid=KID, algorithm="ES256", **claim_overrides):
        now = int(time.time())
        claims = {"sub": "user-123", "email": "responder@example.com", "aud": AUDIENCE,
                  "iss": ISSUER, "iat": now, "exp": now + 3600, "role": "authenticated"}
        claims.update(claim_overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        headers = {"kid": kid} if kid else {}
        return jwt.encode(claims, key if key is not None else signing_key,
                          algorithm=algorithm, headers=headers)
    return make


@pytest.fixture
def seeded(raw_client, seed_scenarios):
    seed_scenarios(raw_client)  # telemetry/surveys are public, so seeding needs no token
    return raw_client


# --- Missing / bad tokens -> 401 -------------------------------------------------

@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_401_without_token(seeded, jwks_calls, method, path):
    r = _call(seeded, method, path)
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"
    assert jwks_calls == []  # rejected before any key lookup


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_200_with_valid_token(seeded, jwks_calls, make_token, method, path):
    r = _call(seeded, method, path, make_token())
    assert r.status_code == 200, r.text


def test_expired_token_401(seeded, jwks_calls, make_token):
    now = int(time.time())
    r = _call(seeded, "get", "/api/cases", make_token(iat=now - 7200, exp=now - 3600))
    assert r.status_code == 401
    assert r.json()["detail"] == "Token expired"


@pytest.mark.parametrize("overrides", [
    {"aud": "anon"},
    {"iss": "https://evil.supabase.co/auth/v1"},
    {"sub": None},
    {"exp": None},
])
def test_wrong_or_missing_claims_401(seeded, jwks_calls, make_token, overrides):
    assert _call(seeded, "get", "/api/cases", make_token(**overrides)).status_code == 401


def test_token_signed_by_other_key_401(seeded, jwks_calls, make_token):
    attacker = ec.generate_private_key(ec.SECP256R1())
    assert _call(seeded, "get", "/api/cases", make_token(key=attacker)).status_code == 401


def test_alg_none_rejected(seeded, jwks_calls, make_token):
    token = make_token(key="", algorithm="none")
    assert _call(seeded, "get", "/api/cases", token).status_code == 401


def test_hs256_token_rejected(seeded, jwks_calls, make_token):
    token = make_token(key="x" * 32, algorithm="HS256")
    assert _call(seeded, "get", "/api/cases", token).status_code == 401


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "Bearer"])
def test_malformed_token_401(seeded, jwks_calls, token):
    assert _call(seeded, "get", "/api/cases", token).status_code == 401


def test_non_bearer_scheme_401(seeded, jwks_calls, make_token):
    assert _call(seeded, "get", "/api/cases", make_token(), scheme="Basic").status_code == 401


def test_token_without_kid_401(seeded, jwks_calls, make_token):
    assert _call(seeded, "get", "/api/cases", make_token(kid=None)).status_code == 401


# --- JWKS caching ---------------------------------------------------------------

def test_jwks_fetched_once_and_cached(seeded, jwks_calls, make_token):
    token = make_token()
    for _ in range(3):
        assert _call(seeded, "get", "/api/units", token).status_code == 200
    assert jwks_calls == [JWKS_URL]


def test_unknown_kid_refetches_once_then_cools_down(seeded, jwks_calls, make_token, monkeypatch):
    assert _call(seeded, "get", "/api/units", make_token()).status_code == 200
    assert len(jwks_calls) == 1
    # Pretend the cached set is older than the cooldown so an unknown kid may refresh.
    auth.jwks_cache._fetched_at -= auth.REFRESH_COOLDOWN_SECONDS + 1
    assert _call(seeded, "get", "/api/units", make_token(kid="rotated")).status_code == 401
    assert len(jwks_calls) == 2
    # Inside the cooldown, more unknown kids don't hit Supabase again.
    assert _call(seeded, "get", "/api/units", make_token(kid="random")).status_code == 401
    assert len(jwks_calls) == 2


def test_jwks_refetched_after_ttl(seeded, jwks_calls, make_token):
    token = make_token()
    assert _call(seeded, "get", "/api/units", token).status_code == 200
    auth.jwks_cache._fetched_at -= auth.JWKS_TTL_SECONDS + 1
    assert _call(seeded, "get", "/api/units", token).status_code == 200
    assert len(jwks_calls) == 2


def test_jwks_unreachable_is_503_not_401(seeded, make_token, monkeypatch):
    monkeypatch.setenv("AUTH_ISSUER_URL", ISSUER)
    monkeypatch.setenv("AUTH_JWKS_URL", JWKS_URL)

    def down(url):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(auth, "fetch_jwks", down)
    auth.jwks_cache.clear()
    try:
        assert _call(seeded, "get", "/api/cases", make_token()).status_code == 503
    finally:
        auth.jwks_cache.clear()


# --- Returned claims ------------------------------------------------------------

def test_dependency_returns_user_claims(jwks_calls, make_token):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=make_token())
    user = auth.verify_supabase_token(creds)
    assert user["user_id"] == "user-123"
    assert user["email"] == "responder@example.com"
    assert user["claims"]["aud"] == AUDIENCE


# --- Public routes stay public --------------------------------------------------

def test_telemetry_public_without_token(raw_client, jwks_calls, telemetry_payload):
    assert raw_client.post("/api/telemetry", json=telemetry_payload()).status_code == 201
    assert jwks_calls == []


def test_surveys_public_without_token(raw_client, jwks_calls):
    import simulator
    survey = next(sc["survey"] for sc in simulator.SCENARIOS.values() if sc["survey"])
    for t in next(sc for sc in simulator.SCENARIOS.values() if sc["survey"])["telemetry"]:
        raw_client.post("/api/telemetry", json=t)
    assert raw_client.post("/api/surveys", json=survey).status_code == 201


@pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json"])
def test_health_and_docs_public(raw_client, path):
    assert raw_client.get(path).status_code == 200
