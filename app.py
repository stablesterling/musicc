import os
import bcrypt
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from ytmusicapi import YTMusic
from pytubefix import YouTube

# --- CRITICAL FIX FOR PYTHON 3.13 & PASSLIB ---
# This fixes: AttributeError: module 'bcrypt' has no attribute '__about__'
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("About", (object,), {"__version__": bcrypt.__version__})

# Your provided Render PostgreSQL URL
DATABASE_URL = "postgresql://vofodb_user:Y7MQfAWwEtsiHQLiGHFV7ikOI2ruTv3u@dpg-d5lm4ongi27c7390kq40-a/vofodb"

# Use 'postgresql://' instead of 'postgres://' for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Password Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

class LikedSong(Base):
    __tablename__ = "liked_songs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    song_id = Column(String)
    title = Column(String)
    artist = Column(String)
    thumbnail = Column(String)

# Initialize Database
Base.metadata.create_all(bind=engine)

app = FastAPI()
yt = YTMusic()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: 
        yield db
    finally: 
        db.close()

# --- Auth ---
@app.post("/api/auth/register")
def register(data: dict, db: Session = Depends(get_db)):
    # Truncate to 72 chars to prevent ValueError: password cannot be longer than 72 bytes
    raw_password = data.get('password', '')[:72]
    hashed_pw = pwd_context.hash(raw_password)
    
    user = User(username=data['username'], password=hashed_pw)
    try:
        db.add(user)
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username already exists or database error")

@app.post("/api/auth/login")
def login(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data['username']).first()
    # Truncate during verification as well
    if not user or not pwd_context.verify(data['password'][:72], user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"success": True, "user_id": user.id, "username": user.username}

# --- Music Engine ---
@app.get("/api/search")
def search(q: str):
    results = yt.search(q, filter="songs")
    return [{"id": r['videoId'], "title": r['title'], "artist": r['artists'][0]['name'], "thumbnail": r['thumbnails'][-1]['url']} for r in results]

@app.get("/api/stream")
def get_stream(id: str):
    try:
        yt_v = YouTube(f"https://www.youtube.com/watch?v={id}", use_oauth=True, allow_oauth_cache=True)
        stream = yt_v.streams.filter(only_audio=True).first()
        return {"url": stream.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/like")
def toggle_like(data: dict, db: Session = Depends(get_db)):
    uid = data.get("user_id")
    existing = db.query(LikedSong).filter(LikedSong.user_id == uid, LikedSong.song_id == data['id']).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"status": "unliked"}
    new_like = LikedSong(user_id=uid, song_id=data['id'], title=data['title'], artist=data['artist'], thumbnail=data['thumbnail'])
    db.add(new_like)
    db.commit()
    return {"status": "liked"}

@app.get("/api/library/{user_id}")
def get_library(user_id: int, db: Session = Depends(get_db)):
    likes = db.query(LikedSong).filter(LikedSong.user_id == user_id).all()
    return [{"id": l.song_id, "title": l.title, "artist": l.artist, "thumbnail": l.thumbnail} for l in likes]

@app.get("/", response_class=HTMLResponse)
def home():
    try:
        with open("index.html", "r") as f: 
            return f.read()
    except FileNotFoundError:
        return "<h1>Vofodb Backend Running</h1><p>index.html not found.</p>"
