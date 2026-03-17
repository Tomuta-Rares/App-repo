import os
from fastapi import FastAPI, HTTPException
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
def create_item(item: ItemCreate):
    db = SessionLocal()
    db_item = Item(name=item.name)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()
    return {"message": "Item created successfully", "item": db_item}

@app.get("/api/items")
def get_items():
    db = SessionLocal()
    items = db.query(Item).all()
    db.close()
    return items