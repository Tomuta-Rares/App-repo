import os
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from auth import extract_realm_roles, extract_username, require_roles

# --- Database setup ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL environment variable")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)


# Create table if not exists
Base.metadata.create_all(bind=engine)

# --- FastAPI app ---
app = FastAPI(
    title="Shopping App API",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# --- CORS ---
origins = [
    "https://shopping.local:8443",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    run_id = request.headers.get("X-Run-Id")
    correlation_id = request.headers.get("X-Correlation-Id")

    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    request.state.run_id = run_id
    request.state.correlation_id = correlation_id

    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id

    return response


# --- Schemas ---
class ItemCreate(BaseModel):
    name: str


# --- Routes ---
@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/items")
def get_items(
    current_user: dict = Depends(require_roles(["reader", "writer", "admin"]))
):
    username = extract_username(current_user)
    roles = extract_realm_roles(current_user)

    db = SessionLocal()
    try:
        items = db.query(Item).all()
        return {
            "message": "items fetched successfully",
            "user": username,
            "roles": roles,
            "items": [{"id": item.id, "name": item.name} for item in items],
        }
    finally:
        db.close()


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