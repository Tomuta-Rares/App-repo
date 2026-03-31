import os
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
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
    token: str = Depends(get_bearer_token),
) -> dict[str, Any]:
    return validate_access_token(token)