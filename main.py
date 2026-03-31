import os
from fastapi import FastAPI, HTTPException, Depends
from auth import (
    get_current_user,
    extract_username,
    extract_realm_roles,
    require_roles,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

# --- Database setup ---
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)

# Create table if not exists
Base.metadata.create_all(bind=engine)

# --- FastAPI app with /api prefix for docs and OpenAPI ---
app = FastAPI(
    title="Shopping App API",
    openapi_url="/api/openapi.json",  # OpenAPI spec served at /api/openapi.json
    docs_url="/api/docs",             # Swagger UI at /api/docs
    redoc_url="/api/redoc"            # Optional ReDoc at /api/redoc
)

# --- CORS setup to allow frontend calls ---
origins = [
    "https://shopping.local:8443",  # Your frontend host
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic schema ---
class ItemCreate(BaseModel):
    name: str

# --- Routes ---
@app.get("/api/health")
def health():
    return {"status": "healthy"}

@app.post("/api/items")
def create_item(
    item: ItemCreate,
    current_user: dict = Depends(require_roles(["writer", "admin"]))
):
    username = extract_username(current_user)
    roles = extract_realm_roles(current_user)

    db = SessionLocal()
    db_item = Item(name=item.name)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()

    return {
        "message": "item created",
        "user": username,
        "roles": roles,
        "item": db_item,
    }



@app.get("/api/items")
def get_items(current_user: dict = Depends(require_roles(["reader", "writer", "admin"]))):
    username = extract_username(current_user)
    roles = extract_realm_roles(current_user)

    db = SessionLocal()
    items = db.query(Item).all()
    db.close()

    return {
        "user": username,
        "roles": roles,
        "items": items,
    }


@app.delete("/api/items/{item_id}")
def delete_item(
    item_id: int,
    current_user: dict = Depends(require_roles(["admin"]))
):
    username = extract_username(current_user)
    roles = extract_realm_roles(current_user)

    db = SessionLocal()
    db_item = db.query(Item).filter(Item.id == item_id).first()

    if not db_item:
        db.close()
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(db_item)
    db.commit()
    db.close()

    return {
        "message": "item deleted",
        "user": username,
        "roles": roles,
        "deleted_item_id": item_id,
    }