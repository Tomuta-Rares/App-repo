# =========================================================
# 🔹 IMPORTURI STANDARD
# =========================================================

import os
import uuid
import json
import logging
import time
import requests

from datetime import datetime, timezone


# =========================================================
# 🔹 FASTAPI + DEPENDENCIES
# =========================================================

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware


# =========================================================
# 🔹 MODELARE DATE
# =========================================================

from pydantic import BaseModel


# =========================================================
# 🔹 DATABASE (SQLAlchemy)
# =========================================================

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# =========================================================
# 🔹 AUTH (Keycloak)
# =========================================================

from auth import extract_realm_roles, extract_username, require_roles


# =========================================================
# 🔹 OPENTELEMETRY (TRACING)
# =========================================================

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import get_current_span


# =========================================================
# 🔹 CONFIGURARE DIN ENV
# =========================================================

LOKI_URL = os.getenv("LOKI_URL")
SERVICE_NAME = os.getenv("SERVICE_NAME", "shopping-app")
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")

OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", SERVICE_NAME)


# =========================================================
# 🔹 LOGGING LOCAL
# =========================================================

logger = logging.getLogger("shopping_app")
logging.basicConfig(level=logging.INFO)


# =========================================================
# 🔹 DATABASE SETUP
# =========================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# =========================================================
# 🔹 MODEL DB
# =========================================================

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)


Base.metadata.create_all(bind=engine)


# =========================================================
# 🔹 FASTAPI APP
# =========================================================

app = FastAPI(
    title="Shopping App API",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


# =========================================================
# 🔹 CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://shopping.local:8443"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# 🔹 OPENTELEMETRY INIT
# =========================================================

resource = Resource.create({
    "service.name": OTEL_SERVICE_NAME,
    "deployment.environment": ENVIRONMENT,
})

tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

if OTEL_EXPORTER_OTLP_ENDPOINT:
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces"
    )

    tracer_provider.add_span_processor(
        BatchSpanProcessor(otlp_exporter)
    )

tracer = trace.get_tracer(__name__)

FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)


# =========================================================
# 🔹 LOG → LOKI
# =========================================================

def send_log_to_loki(log_payload: dict):
    if not LOKI_URL:
        return

    loki_payload = {
        "streams": [{
            "stream": {
                "service": SERVICE_NAME,
                "env": ENVIRONMENT,
                "component": "backend",
            },
            "values": [[
                str(int(time.time() * 1_000_000_000)),
                json.dumps(log_payload)
            ]]
        }]
    }

    try:
        requests.post(LOKI_URL, json=loki_payload, timeout=2).raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send log to Loki: {e}")


# =========================================================
# 🔹 CORRELATION + LOGGING MIDDLEWARE
# =========================================================

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):

    start_time = time.time()

    run_id = request.headers.get("X-Run-Id")
    correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())

    request.state.run_id = run_id
    request.state.correlation_id = correlation_id

    # 🔹 USER INFO (dacă există)
    user = None
    roles = []

    if hasattr(request.state, "user"):
        payload = request.state.user
        user = extract_username(payload)
        roles = extract_realm_roles(payload)

    # 🔹 TRACE
    span = get_current_span()
    span_context = span.get_span_context()

    trace_id = None
    if span_context and span_context.trace_id != 0:
        trace_id = format(span_context.trace_id, "032x")

    try:
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        status_code = response.status_code
        error_class = None
        return response

    except Exception as exc:
        status_code = 500
        error_class = type(exc).__name__
        raise

    finally:
        latency_ms = round((time.time() - start_time) * 1000, 2)

        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": SERVICE_NAME,
            "env": ENVIRONMENT,
            "method": request.method,
            "path": request.url.path,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "trace_id": trace_id,
            "user": user,
            "roles": roles,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "error_class": error_class,
        }

        logger.info(json.dumps(log_payload))

        if request.url.path != "/api/health":
            send_log_to_loki(log_payload)


# =========================================================
# 🔹 SCHEMA
# =========================================================

class ItemCreate(BaseModel):
    name: str


# =========================================================
# 🔹 ROUTES
# =========================================================

@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/items")
def get_items(
    current_user: dict = Depends(require_roles(["reader", "writer", "admin"]))
):
    with tracer.start_as_current_span("get_items_logic"):
        db = SessionLocal()
        try:
            items = db.query(Item).all()
            return {"items": [{"id": i.id, "name": i.name} for i in items]}
        finally:
            db.close()


@app.post("/api/items")
def create_item(
    item: ItemCreate,
    current_user: dict = Depends(require_roles(["writer", "admin"]))
):
    db = SessionLocal()
    try:
        db_item = Item(name=item.name)
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return {"item": {"id": db_item.id, "name": db_item.name}}
    finally:
        db.close()


@app.delete("/api/items/{item_id}")
def delete_item(
    item_id: int,
    current_user: dict = Depends(require_roles(["admin"]))
):
    db = SessionLocal()
    try:
        db_item = db.query(Item).filter(Item.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail="Item not found")

        db.delete(db_item)
        db.commit()

        return {"deleted_item_id": item_id}
    finally:
        db.close()