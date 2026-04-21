# =========================================================
# IMPORTURI DE BAZĂ
# =========================================================
# Aceste librării ne ajută cu:
# - citirea variabilelor de mediu (os)
# - generarea de ID-uri unice pentru request-uri (uuid)
# - serializarea logurilor în JSON (json)
# - logging local în stdout/stderr (logging)
# - măsurarea timpului de execuție (time)
# - trimiterea logurilor către Loki prin HTTP (requests)
import os
import uuid
import json
import logging
import time
import requests


# =========================================================
# FASTAPI + MIDDLEWARE
# =========================================================
# FastAPI este framework-ul web.
# - Depends: pentru dependency injection (ex: auth/RBAC)
# - FastAPI: aplicația propriu-zisă
# - HTTPException: erori HTTP controlate
# - Request: acces la request-ul curent
# - status: constante HTTP (200, 201, 404 etc.)
#
# CORSMiddleware este folosit pentru a permite frontend-ului
# din browser să apeleze backend-ul fără blocaje CORS.
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware


# =========================================================
# VALIDARE INPUT
# =========================================================
# Pydantic ne ajută să definim și să validăm schema input-ului
# primit în body-ul request-urilor.
from pydantic import BaseModel


# =========================================================
# SQLALCHEMY / DATABASE
# =========================================================
# SQLAlchemy este folosit ca ORM / layer de acces la baza de date.
# - Column, Integer, String: definirea coloanelor
# - create_engine: conexiunea la DB
# - declarative_base: baza pentru modelele ORM
# - sessionmaker: factory pentru sesiuni DB
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker



# =========================================================
# AUTH / RBAC
# =========================================================
# Aceste funcții vin din auth.py și fac integrarea cu Keycloak:
# - extract_realm_roles: scoate rolurile din token
# - extract_username: scoate username-ul din token
# - require_roles: verifică dacă userul are rolurile necesare
from auth import extract_realm_roles, extract_username, require_roles


# =========================================================
# TIMESTAMP UTC
# =========================================================
# Folosim datetime + timezone pentru a scrie timestamp-uri clare
# și consistente în loguri.
from datetime import datetime, timezone


# =========================================================
# OPENTELEMETRY / TRACING
# =========================================================
# Aici sunt importurile pentru distributed tracing:
# - trace: API-ul principal OpenTelemetry
# - get_current_span: ne lasă să luăm span-ul activ curent
# - OTLPSpanExporter: trimite trace-urile către Tempo
# - FastAPIInstrumentor: creează automat spans pentru request-uri HTTP
# - SQLAlchemyInstrumentor: creează automat spans pentru query-urile DB
# - Resource: definește metadata despre serviciu (ex: service.name)
# - TracerProvider: provider-ul global de tracing
# - BatchSpanProcessor: trimite spans în batch, nu unul câte unul
from opentelemetry import trace
from opentelemetry.trace import get_current_span
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


# =========================================================
# CONFIGURARE DIN VARIABILE DE MEDIU
# =========================================================
# Toate aceste valori vin din Kubernetes / Helm values.
# Ideea este să nu hardcodăm configurația în cod.
#
# - LOKI_URL: endpoint-ul Loki unde trimitem logurile
# - SERVICE_NAME: numele serviciului, folosit în logs și tracing
# - ENVIRONMENT: mediul curent (ex: local)
# - OTEL_EXPORTER_OTLP_ENDPOINT: baza URL-ului pentru export către Tempo
# - OTEL_SERVICE_NAME: numele sub care serviciul apare în tracing
LOKI_URL = os.getenv("LOKI_URL")
SERVICE_NAME = os.getenv("SERVICE_NAME", "shopping-app")
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", SERVICE_NAME)


# =========================================================
# LOGGING LOCAL
# =========================================================
# Configurăm logger-ul standard Python.
# Acesta scrie logurile și local (stdout/stderr), nu doar în Loki.
# E util ca fallback și pentru debugging în pod.
logger = logging.getLogger("shopping_app")
logging.basicConfig(level=logging.INFO)


# =========================================================
# DATABASE SETUP
# =========================================================
# Citim URL-ul bazei de date din env.
# Dacă lipsește, aplicația nu poate porni corect.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL environment variable")

# create_engine creează conexiunea logică la DB.
# pool_pre_ping=True ajută la evitarea conexiunilor moarte.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# SessionLocal este factory-ul din care deschidem sesiuni DB în endpoints.
SessionLocal = sessionmaker(bind=engine)

# Base este clasa de bază pentru modelele noastre ORM.
Base = declarative_base()


# =========================================================
# MODELUL ORM PENTRU TABELA "items"
# =========================================================
# Acesta este modelul Python care corespunde tabelei items din MySQL.
class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)


# =========================================================
# CREAREA TABELELOR (LOCAL / LAB)
# =========================================================
# Dacă tabela nu există, o creează.
# Pentru proiectul tău local e ok.
# În producție, de obicei ai migrații dedicate, nu create_all în aplicație.
Base.metadata.create_all(bind=engine)


# =========================================================
# INIȚIALIZAREA APLICAȚIEI FASTAPI
# =========================================================
# Setăm titlul și endpoint-urile pentru docs / openapi.
app = FastAPI(
    title="Shopping App API",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


# =========================================================
# CONFIGURARE CORS
# =========================================================
# Permitem frontend-ului găzduit la shopping.local:8443
# să facă request-uri către backend.
origins = [
    "https://shopping.local:8443",
]


# =========================================================
# RESOURCE PENTRU OPENTELEMETRY
# =========================================================
# Resource descrie "cine produce trace-urile".
# service.name este foarte important: așa apare serviciul în Tempo/Grafana.
resource = Resource.create({
    "service.name": OTEL_SERVICE_NAME,
    "deployment.environment": ENVIRONMENT,
})


# =========================================================
# TRACER PROVIDER GLOBAL
# =========================================================
# TracerProvider este inima OpenTelemetry în aplicația ta.
# Îl setăm global ca instrumentările și span-urile manuale să îl folosească.
tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)


# =========================================================
# EXPORTER OTLP CĂTRE TEMPO
# =========================================================
# Dacă avem endpoint configurat, construim exporter-ul și îl atașăm.
# /v1/traces este ruta standard pentru exportul OTLP HTTP de trace-uri.
if OTEL_EXPORTER_OTLP_ENDPOINT:
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces"
    )
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)


# =========================================================
# TRACERUL FOLOSIT PENTRU SPANS MANUALE
# =========================================================
# Cu acest tracer pornim spans manuale, de exemplu pentru business logic.
tracer = trace.get_tracer(__name__)


# =========================================================
# AUTO-INSTRUMENTATION
# =========================================================
# Activăm tracing automat pentru:
# - FastAPI: creează server spans pentru request-urile HTTP
# - SQLAlchemy: creează spans pentru query-urile DB
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)


# =========================================================
# MIDDLEWARE CORS
# =========================================================
# Îl adăugăm după configurarea originii permise.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# FUNCȚIE: TRIMITERE LOG CĂTRE LOKI
# =========================================================
# Primește un dict Python (log_payload), îl transformă în JSON și îl trimite
# către Loki folosind formatul așteptat de API-ul Loki.
def send_log_to_loki(log_payload: dict) -> None:
    # Dacă nu avem URL-ul Loki, ieșim fără eroare.
    if not LOKI_URL:
        return

    # Serializăm logul în JSON string.
    log_line = json.dumps(log_payload)

    # Loki așteaptă timestamp în nanosecunde.
    timestamp_ns = str(int(time.time() * 1_000_000_000))

    # Formatul minim cerut de Loki:
    # streams -> stream(labels) + values([timestamp, logline])
    loki_payload = {
        "streams": [
            {
                "stream": {
                    "service": SERVICE_NAME,
                    "env": ENVIRONMENT,
                    "component": "backend",
                },
                "values": [
                    [timestamp_ns, log_line]
                ],
            }
        ]
    }

    # requests.post(...).raise_for_status() va ridica excepție dacă Loki răspunde
    # cu eroare (4xx/5xx).
    requests.post(
        LOKI_URL,
        json=loki_payload,
        timeout=2,
    ).raise_for_status()


# =========================================================
# MIDDLEWARE: CORRELATION + LOGGING + TRACE CORRELATION
# =========================================================
# Acest middleware rulează pentru fiecare request HTTP.
#
# Rolurile lui sunt:
# 1. citește / generează run_id și correlation_id
# 2. le pune în request.state
# 3. propagă correlation_id în response header
# 4. măsoară latența request-ului
# 5. extrage user/roles dacă există auth
# 6. extrage trace_id/span_id din span-ul activ OpenTelemetry
# 7. scrie log local și îl trimite în Loki
@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    # Salvăm momentul de start ca să calculăm latența totală.
    start_time = time.time()

    # Luăm run_id și correlation_id din headers, dacă există.
    run_id = request.headers.get("X-Run-Id")
    correlation_id = request.headers.get("X-Correlation-Id")

    # Dacă request-ul nu vine cu correlation_id, generăm unul nou.
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    # Salvăm valorile în request.state ca să poată fi folosite și mai târziu.
    request.state.run_id = run_id
    request.state.correlation_id = correlation_id

    # Valori default; pot fi suprascrise în try / except.
    response = None
    status_code = 500
    error_class = None

    try:
        # Lăsăm request-ul să meargă mai departe către endpoint.
        response = await call_next(request)

        # După ce endpoint-ul termină, reținem status code-ul.
        status_code = response.status_code

        # Propagăm correlation_id în response, ca să-l poată vedea clientul.
        response.headers["X-Correlation-Id"] = correlation_id
        return response

    except Exception as exc:
        # Dacă apare o eroare necontrolată, salvăm clasa erorii pentru logging.
        error_class = type(exc).__name__
        raise

    finally:
        # Calculăm latența totală a request-ului în milisecunde.
        latency_ms = round((time.time() - start_time) * 1000, 2)

        # Dacă auth.py a pus userul în request.state, îl preluăm de acolo.
        user_payload = getattr(request.state, "user", None)

        username = None
        roles = []

        if user_payload:
            username = extract_username(user_payload)
            roles = extract_realm_roles(user_payload)

        # Luăm span-ul activ curent din OpenTelemetry.
        # Dacă request-ul este instrumentat corect, aici avem contextul activ.
        current_span = get_current_span()
        span_context = current_span.get_span_context()

        trace_id = None
        span_id = None

        # Dacă span_context este valid, extragem trace_id și span_id.
        # Le convertim în hex string, pentru că așa sunt mai ușor de căutat.
        if span_context and span_context.is_valid:
            trace_id = format(span_context.trace_id, "032x")
            span_id = format(span_context.span_id, "016x")

        # Construim logul structurat.
        # Aici este punctul unde se face corelarea logs ↔ traces.
        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": SERVICE_NAME,
            "env": ENVIRONMENT,
            "message": "request completed",
            "method": request.method,
            "path": request.url.path,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "trace_id": trace_id,
            "span_id": span_id,
            "user": username,
            "roles": roles,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "error_class": error_class,
        }

        # Scriem logul și local.
        logger.info(json.dumps(log_payload))

        # Evităm să trimitem /api/health în Loki ca să nu umplem logurile cu noise.
        if request.url.path != "/api/health":
            try:
                send_log_to_loki(log_payload)
            except requests.RequestException as exc:
                # Dacă Loki nu răspunde, nu stricăm request-ul utilizatorului.
                # Scriem doar un warning local.
                logger.warning(
                    json.dumps(
                        {
                            "message": "failed to send log to loki",
                            "error_class": type(exc).__name__,
                        }
                    )
                )


# =========================================================
# SCHEMA PENTRU CREATE ITEM
# =========================================================
# Aceasta definește forma body-ului pentru POST /api/items
# și validează că există câmpul name.
class ItemCreate(BaseModel):
    name: str


# =========================================================
# HEALTHCHECK
# =========================================================
# Endpoint simplu pentru probes și verificare rapidă.
@app.get("/api/health")
def health():
    return {"status": "healthy"}


# =========================================================
# GET /api/items
# =========================================================
# Permite reader / writer / admin.
# Aici am pus și un span manual pentru business logic:
# get_items_logic
@app.get("/api/items")
def get_items(
    current_user: dict = Depends(require_roles(["reader", "writer", "admin"]))
):
    username = extract_username(current_user)
    roles = extract_realm_roles(current_user)

    # Span manual: ne ajută să separăm logica aplicației de restul request-ului.
    with tracer.start_as_current_span("get_items_logic"):
        db = SessionLocal()
        try:
            #db.execute(text("SELECT SLEEP(0.2)"))
            items = db.query(Item).all()
            return {
                "message": "items fetched successfully",
                "user": username,
                "roles": roles,
                "items": [{"id": item.id, "name": item.name} for item in items],
            }
        finally:
            db.close()


# =========================================================
# POST /api/items
# =========================================================
# Permite writer / admin.
# Creează un item nou în DB și îl returnează.
@app.post("/api/items", status_code=status.HTTP_201_CREATED)
def create_item(
    item: ItemCreate,
    current_user: dict = Depends(require_roles(["writer", "admin"])),
):
    username = extract_username(current_user)
    roles = extract_realm_roles(current_user)

    db = SessionLocal()
    try:
        db_item = Item(name=item.name)
        db.add(db_item)
        db.commit()
        db.refresh(db_item)

        return {
            "message": "item created",
            "user": username,
            "roles": roles,
            "item": {"id": db_item.id, "name": db_item.name},
        }
    finally:
        db.close()


# =========================================================
# DELETE /api/items/{item_id}
# =========================================================
# Permite doar admin.
# Șterge un item dacă există; dacă nu există, întoarce 404.
@app.delete("/api/items/{item_id}")
def delete_item(
    item_id: int,
    current_user: dict = Depends(require_roles(["admin"])),
):
    username = extract_username(current_user)
    roles = extract_realm_roles(current_user)

    db = SessionLocal()
    try:
        db_item = db.query(Item).filter(Item.id == item_id).first()

        if not db_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found",
            )

        db.delete(db_item)
        db.commit()

        return {
            "message": "item deleted",
            "user": username,
            "roles": roles,
            "deleted_item_id": item_id,
        }
    finally:
        db.close()