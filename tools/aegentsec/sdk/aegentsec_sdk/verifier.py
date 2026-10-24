import asyncio
import time

import httpx
import jwt
from pydantic import BaseModel, Field


class AgentIdentity(BaseModel):
    agent_id: str = Field(min_length=1)
    enterprise_id: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    scopes: set[str]


class TokenVerificationError(Exception):
    pass


class AegentSecVerifier:
    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_url: str,
        cache_seconds: int = 300,
        min_refetch_seconds: int = 30,
    ):
        self.issuer = issuer
        self.audience = audience
        self.jwks_url = jwks_url
        self.cache_seconds = cache_seconds
        self._keys: dict[str, dict] = {}
        self._cached_until = 0.0
        self.min_refetch_seconds = min_refetch_seconds
        self._last_fetch: float | None = None
        self._lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _may_refetch(self, kid: str) -> bool:
        now = time.monotonic()
        if self._last_fetch is None or now >= self._cached_until:
            return True
        # An unknown kid may mean key rotation, but unauthenticated callers choose the kid,
        # so refetching is rate limited to keep them from driving traffic to the IAM service.
        return kid not in self._keys and now - self._last_fetch >= self.min_refetch_seconds

    async def _fetch(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=5.0)
        try:
            response = await self._http.get(self.jwks_url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TokenVerificationError("JWKS unavailable") from exc
        self._keys = {
            key["kid"]: key
            for key in document.get("keys", [])
            if key.get("kty") == "RSA" and key.get("alg") == "RS256" and "kid" in key
        }
        self._last_fetch = time.monotonic()
        self._cached_until = self._last_fetch + self.cache_seconds

    async def _key(self, kid: str) -> dict:
        if self._may_refetch(kid):
            async with self._lock:
                if self._may_refetch(kid):
                    await self._fetch()
        if kid not in self._keys:
            raise TokenVerificationError("Unknown signing key")
        return self._keys[kid]

    async def verify(self, token: str) -> AgentIdentity:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise TokenVerificationError("Unsupported token header")
            jwk = await self._key(header["kid"])
            public_key = jwt.PyJWK.from_dict(jwk).key
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "client_id",
                        "enterprise_id",
                        "iat",
                        "exp",
                        "jti",
                    ]
                },
            )
            return AgentIdentity(
                agent_id=claims["sub"],
                enterprise_id=claims["enterprise_id"],
                client_id=claims["client_id"],
                scopes=set(claims.get("scope", "").split()),
            )
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise TokenVerificationError("Invalid access token") from exc

    def require_scope(self, required_scope: str):
        from aegentsec_sdk.dependencies import require_scope

        return require_scope(self, required_scope)
