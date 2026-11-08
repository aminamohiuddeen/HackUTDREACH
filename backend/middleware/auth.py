"""Supabase JWT verification for REACH.

Supabase signs access tokens with ES256 (asymmetric). We verify them against the
project's public JWKS, which is fetched over HTTPS and cached in memory.

Security notes:
- The algorithm allowlist is hardcoded to ["ES256"]. The token header's `alg`
  is never trusted, so "none"/HS256 key-confusion tricks are rejected.
- The token header's `kid` only selects WHICH published key to try; an unknown
  kid triggers at most one JWKS refresh per REFRESH_COOLDOWN_SECONDS so random
  kids can't be used to hammer Supabase.
- Config is read from the environment at call time so tests can monkeypatch it.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALLOWED_ALGORITHMS = ["ES256"]  # never derived from the token
JWKS_TTL_SECONDS = 3600
REFRESH_COOLDOWN_SECONDS = 30
JWKS_FETCH_TIMEOUT_SECONDS = 5.0

_DEFAULT_ISSUER = "https://pvwsdtvvyscyqgqsfnie.supabase.co/auth/v1"
_DEFAULT_JWKS_URL = f"{_DEFAULT_ISSUER}/.well-known/jwks.json"
_DEFAULT_AUDIENCE = "authenticated"

bearer_scheme = HTTPBearer(auto_error=False)


def _issuer() -> str:
    return os.getenv("AUTH_ISSUER_URL") or _DEFAULT_ISSUER


def _jwks_url() -> str:
    return os.getenv("AUTH_JWKS_URL") or _DEFAULT_JWKS_URL


def _audience() -> str:
    return os.getenv("AUTH_AUDIENCE") or _DEFAULT_AUDIENCE


# --- JWKS cache --------------------------------------------------------------

class _JWKSCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._url: str | None = None

    def clear(self) -> None:
        with self._lock:
            self._keys, self._fetched_at, self._url = {}, 0.0, None

    def _refresh_locked(self, url: str) -> None:
        jwks = fetch_jwks(url)
        keys: dict[str, Any] = {}
        for jwk in jwks.get("keys", []):
            kid = jwk.get("kid")
            if not kid or jwk.get("kty") != "EC" or jwk.get("use", "sig") != "sig":
                continue
            try:
                keys[kid] = jwt.PyJWK(jwk, algorithm="ES256").key
            except jwt.PyJWKError:
                continue  # skip keys we can't use rather than failing the whole set
        self._keys, self._fetched_at, self._url = keys, time.monotonic(), url

    def get_key(self, kid: str) -> Any | None:
        url = _jwks_url()
        with self._lock:
            now = time.monotonic()
            stale = (self._url != url or not self._keys
                     or now - self._fetched_at > JWKS_TTL_SECONDS)
            if stale:
                self._refresh_locked(url)
            elif kid not in self._keys and now - self._fetched_at > REFRESH_COOLDOWN_SECONDS:
                self._refresh_locked(url)  # key rotation: refetch once for an unknown kid
            return self._keys.get(kid)


def fetch_jwks(url: str) -> dict:
    """Fetch the JWKS document. Separate function so tests can mock it."""
    resp = httpx.get(url, timeout=JWKS_FETCH_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


jwks_cache = _JWKSCache()


# --- Dependency --------------------------------------------------------------

def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def verify_supabase_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """FastAPI dependency: returns {"user_id", "email", "claims"} or raises 401."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized("Missing bearer token")
    token = credentials.credentials

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise _unauthorized("Malformed token")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise _unauthorized("Token has no key id")

    try:
        key = jwks_cache.get_key(kid)
    except (httpx.HTTPError, ValueError):
        # Our problem, not the client's: don't blame their token.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Auth key service unavailable")
    if key is None:
        raise _unauthorized("Unknown signing key")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=_audience(),
            issuer=_issuer(),
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token")

    return {"user_id": claims["sub"], "email": claims.get("email"), "claims": claims}
