import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

# --- Database setup ---
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# --- Simple authentication token ---
API_TOKEN = "supersecrettoken"  # token for login
security = HTTPBearer()          # FastAPI helper to read Authorization header

# --- Database model ---
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
    redoc_url="/api/redoc"
)

# --- CORS setup so frontend can call the API ---
origins = [
    "https://shopping.local:8443",  # your frontend host
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Pydantic schemas (data validation)
# -------------------------
class ItemCreate(BaseModel):
    name: str

class LoginRequest(BaseModel):
    username: str
    password: str

# -------------------------
# Auth dependency
# -------------------------
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    This function runs automatically when a route has `Depends(verify_token)`.
    It reads the Authorization header and checks if the token is correct.
    """
    if credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

# -------------------------
# Routes
# -------------------------
@app.get("/api/health")
def health():
    return {"status": "healthy"}

@app.post("/api/login")
def login(data: LoginRequest):
    """
    This endpoint is called by the frontend when user clicks "Login".
    If username/password are correct, it returns a token.
    """
    if data.username == "admin" and data.password == "admin":
        return {"token": API_TOKEN}

    raise HTTPException(status_code=401, detail="Invalid username or password")

@app.get("/api/items", dependencies=[Depends(verify_token)])
def get_items():
    db = SessionLocal()
    items = db.query(Item).all()
    db.close()
    return items

@app.post("/api/items", dependencies=[Depends(verify_token)])
def create_item(item: ItemCreate):
    db = SessionLocal()
    db_item = Item(name=item.name)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()
    return {"message": "Item created successfully", "item": db_item}