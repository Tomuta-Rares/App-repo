# =========================================================
# IMPORTURI
# =========================================================

import os
from typing import Any, Callable

import jwt

# FastAPI:
# - Depends: permite dependency injection în endpoints
# - Header: citește valori din header-ele HTTP
# - HTTPException: generează răspunsuri HTTP controlate
# - status: constante pentru coduri HTTP, ex: 401, 403
# - Request: obiectul request-ului curent
from fastapi import Depends, Header, HTTPException, status, Request

# PyJWT:
# - ExpiredSignatureError: token JWT expirat
# - InvalidTokenError: token JWT invalid
# - PyJWKClient: client care descarcă cheia publică de la Keycloak
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient


# =========================================================
# CONFIGURARE KEYCLOAK DIN VARIABILE DE MEDIU
# =========================================================
# Aceste valori vin din Kubernetes / Helm values.
# Nu le hardcodăm în cod pentru că diferă între medii.
#
# KEYCLOAK_ISSUER:
# Identitatea serverului care a emis token-ul.
# Exemplu:
# https://auth.local:8443/auth/realms/devops-lvlup
#
# KEYCLOAK_JWKS_URL:
# Endpoint-ul unde Keycloak publică cheile publice folosite pentru
# verificarea semnăturii JWT.
KEYCLOAK_ISSUER = os.getenv("KEYCLOAK_ISSUER")
KEYCLOAK_JWKS_URL = os.getenv("KEYCLOAK_JWKS_URL")


# =========================================================
# VALIDARE CONFIG LA STARTUP
# =========================================================
# Dacă lipsesc aceste variabile, aplicația nu poate valida token-uri.
# Alegem să oprim aplicația imediat, în loc să rulăm într-o stare nesigură.
if not KEYCLOAK_ISSUER:
    raise RuntimeError("Missing KEYCLOAK_ISSUER environment variable")

if not KEYCLOAK_JWKS_URL:
    raise RuntimeError("Missing KEYCLOAK_JWKS_URL environment variable")


# =========================================================
# JWKS CLIENT
# =========================================================
# Keycloak semnează token-urile JWT cu o cheie privată.
# Aplicația noastră verifică token-ul folosind cheia publică.
#
# PyJWKClient știe să:
# - citească header-ul token-ului JWT
# - găsească key id-ul (kid)
# - descarce cheia publică potrivită din JWKS URL
jwk_client = PyJWKClient(KEYCLOAK_JWKS_URL)


# =========================================================
# EXTRAGERE TOKEN DIN HEADER
# =========================================================
# Request-urile autentificate trebuie să trimită:
#
# Authorization: Bearer <access_token>
#
# Această funcție NU validează token-ul.
# Ea doar îl extrage din header și verifică formatul.
def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    # Dacă header-ul Authorization lipsește complet,
    # clientul nu este autentificat.
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    # Standardul folosit este Bearer Token.
    # Dacă header-ul nu începe cu "Bearer ", formatul este greșit.
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    # Scoatem prefixul "Bearer " și păstrăm doar token-ul.
    token = authorization.removeprefix("Bearer ").strip()

    # Dacă după prefix nu există token real, request-ul este invalid.
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    return token


# =========================================================
# VALIDARE ACCESS TOKEN
# =========================================================
# Această funcție verifică dacă token-ul primit:
# - este semnat corect de Keycloak
# - folosește algoritmul așteptat
# - a fost emis de issuer-ul corect
# - nu este expirat
#
# Dacă token-ul este valid, returnăm payload-ul JWT.
# Payload-ul conține informații precum username, roles, issuer etc.
def validate_access_token(token: str) -> dict[str, Any]:
    try:
        # Obținem cheia publică potrivită pentru token.
        # JWT-ul are în header un "kid", iar PyJWKClient îl folosește
        # ca să selecteze cheia corectă din JWKS.
        signing_key = jwk_client.get_signing_key_from_jwt(token)

        # Decodăm și validăm token-ul.
        #
        # Verificări importante:
        # - semnătura token-ului
        # - algoritmul RS256
        # - issuer-ul Keycloak
        #
        # verify_aud=False:
        # În proiectul local nu verificăm audience-ul.
        # Pentru producție, de obicei ar trebui validat și aud/client-ul.
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER,
            options={"verify_aud": False},
        )

        return payload

    # Token-ul a fost valid cândva, dar a expirat.
    # Clientul trebuie să obțină un token nou.
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )

    # Token-ul este invalid:
    # - semnătură greșită
    # - issuer greșit
    # - format invalid
    # - token modificat manual
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


# =========================================================
# OBȚINERE USER CURENT
# =========================================================
# Această funcție este dependency FastAPI.
#
# Flow:
# 1. extrage Bearer token-ul din header
# 2. validează token-ul
# 3. returnează payload-ul userului
# 4. salvează userul în request.state pentru logging/observability
def get_current_user(
    request: Request,
    token: str = Depends(get_bearer_token),
) -> dict[str, Any]:
    # Validăm token-ul și obținem payload-ul JWT.
    payload = validate_access_token(token)

    # Salvăm payload-ul în request.state.
    #
    # De ce?
    # Middleware-ul de logging poate citi ulterior:
    # - username
    # - roles
    #
    # Asta permite loguri structurate de tip:
    # user=alice, roles=["writer"], correlation_id=..., trace_id=...
    request.state.user = payload

    return payload


# =========================================================
# EXTRAGERE USERNAME DIN JWT
# =========================================================
# Keycloak pune de obicei username-ul în câmpul preferred_username.
# Dacă lipsește, folosim "unknown" ca fallback.
def extract_username(payload: dict[str, Any]) -> str:
    return payload.get("preferred_username", "unknown")


# =========================================================
# EXTRAGERE REALM ROLES DIN JWT
# =========================================================
# În proiectul tău ai ales să folosești realm roles.
#
# Keycloak pune aceste roluri în payload sub forma:
#
# "realm_access": {
#   "roles": ["reader", "writer", "admin"]
# }
#
# Această funcție extrage lista de roluri într-un mod defensiv.
def extract_realm_roles(payload: dict[str, Any]) -> list[str]:
    # Luăm obiectul realm_access.
    # Dacă lipsește, folosim dict gol.
    realm_access = payload.get("realm_access", {})

    # Luăm lista de roluri.
    # Dacă lipsește, folosim listă goală.
    roles = realm_access.get("roles", [])

    # Ne asigurăm că roles chiar este listă.
    # Dacă token-ul are format neașteptat, nu vrem să crape aplicația.
    if not isinstance(roles, list):
        return []

    # Returnăm doar valorile care sunt string-uri.
    # Este o mică protecție împotriva payload-urilor neașteptate.
    return [role for role in roles if isinstance(role, str)]


# =========================================================
# RBAC - ROLE BASED ACCESS CONTROL
# =========================================================
# require_roles este o funcție-factory.
#
# Primește lista de roluri acceptate pentru un endpoint și întoarce
# o dependency FastAPI care verifică userul curent.
#
# Exemplu:
#
# @app.get("/api/items")
# def get_items(
#     current_user: dict = Depends(require_roles(["reader", "writer", "admin"]))
# ):
#     ...
#
# Asta înseamnă:
# - token valid este obligatoriu
# - userul trebuie să aibă cel puțin unul dintre rolurile permise
def require_roles(allowed_roles: list[str]) -> Callable[..., dict[str, Any]]:
    # Această funcție interioară este dependency-ul real folosit de FastAPI.
    def role_checker(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        # Extragem rolurile userului din JWT.
        user_roles = extract_realm_roles(current_user)

        # Verificăm dacă userul are cel puțin un rol permis.
        #
        # Exemplu:
        # allowed_roles = ["writer", "admin"]
        # user_roles = ["reader"]
        # => acces respins
        #
        # allowed_roles = ["writer", "admin"]
        # user_roles = ["writer"]
        # => acces permis
        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )

        # Dacă verificarea a trecut, returnăm userul către endpoint.
        return current_user

    # Returnăm dependency-ul configurat cu rolurile cerute.
    return role_checker