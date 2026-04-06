import os
from typing import Any, Callable

import jwt
from fastapi import Depends, Header, HTTPException, status, Request
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient

KEYCLOAK_ISSUER = os.getenv("KEYCLOAK_ISSUER")
KEYCLOAK_JWKS_URL = os.getenv("KEYCLOAK_JWKS_URL")

if not KEYCLOAK_ISSUER:
    raise RuntimeError("Missing KEYCLOAK_ISSUER environment variable")

if not KEYCLOAK_JWKS_URL:
    raise RuntimeError("Missing KEYCLOAK_JWKS_URL environment variable")

jwk_client = PyJWKClient(KEYCLOAK_JWKS_URL)


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    token = authorization.removeprefix("Bearer ").strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    return token


def validate_access_token(token: str) -> dict[str, Any]:
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER,
            options={"verify_aud": False},
        )

        return payload

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def get_current_user(
    request: Request,
    token: str = Depends(get_bearer_token),
) -> dict[str, Any]:
    payload = validate_access_token(token)

    # 👇 salvăm în request.state
    request.state.user = payload

    return payload


def extract_username(payload: dict[str, Any]) -> str:
    return payload.get("preferred_username", "unknown")


def extract_realm_roles(payload: dict[str, Any]) -> list[str]:
    realm_access = payload.get("realm_access", {})
    roles = realm_access.get("roles", [])

    if not isinstance(roles, list):
        return []

    return [role for role in roles if isinstance(role, str)]


def require_roles(allowed_roles: list[str]) -> Callable[..., dict[str, Any]]:
    def role_checker(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        user_roles = extract_realm_roles(current_user)

        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )

        return current_user

    return role_checker