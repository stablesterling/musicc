import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from yt_dlp import YoutubeDL

# ---------------- APP SETUP ----------------

app = Flask(__name__, static_folder=".", static_url_path="")

database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "vofo_ultra_secret_2026"),
    SQLALCHEMY_DATABASE_URI=database_url or "sqlite:///vofo.db",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True if database_url else False
)

CORS(app, supports_credentials=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "index"

HEADERS = {
    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
}

# ---------------- DATABASE MODELS ----------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    likes = db.relationship("LikedTrack", backref="user", lazy=True)

class LikedTrack(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    artist = db.Column(db.String(200))
    thumbnail = db.Column(db.String(500))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# -------- AUTH --------

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json

    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "User already exists"}), 400

    hashed_pw = generate_password_hash(data["password"], method="pbkdf2:sha256")
    user = User(username=data["username"], password=hashed_pw)

    db.session.add(user)
    db.session.commit()

    return jsonify({"success": True})

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data["username"]).first()

    if user and check_password_hash(user.password, data["password"]):
        login_user(user, remember=True)
        return jsonify({"success": True, "username": user.username})

    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/auth/logout")
def logout():
    logout_user()
    return jsonify({"success": True})

@app.route("/api/auth/status")
def status():
    if current_user.is_authenticated:
        return jsonify({"logged_in": True, "username": current_user.username})
    return jsonify({"logged_in": False})

# -------- SEARCH --------

@app.route("/api/search")
@login_required
def search():
    query = request.args.get("q")
    if not query:
        return jsonify([])

    try:
        ydl_opts = {
            "quiet": True,
            "noplaylist": True,
            "extract_flat": True,
            "http_headers": HEADERS
        }

        with YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(f"scsearch10:{query}", download=False)

            results = []
            for e in data.get("entries", []):
                if not e:
                    continue
                results.append({
                    "id": e.get("url"),
                    "title": e.get("title"),
                    "artist": e.get("uploader") or "SoundCloud Artist",
                    "thumbnail": e.get("thumbnail")
                    or "https://placehold.co/50x50?text=No+Cover"
                })

            return jsonify(results)

    except Exception:
        return jsonify([])

# -------- PLAY (FIXED & STABLE) --------

@app.route("/api/play", methods=["POST"])
@login_required
def play():
    track_url = request.json.get("url")

    if not track_url:
        return jsonify({"error": "Missing track URL"}), 400

    try:
        ydl_opts = {
            # FORCE browser-compatible progressive audio
            "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio",
            "quiet": True,
            "http_headers": HEADERS,
            "nocheckcertificate": True,
            "cachedir": False,
            "noplaylist": True
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(track_url, download=False)

            stream_url = info.get("url")
            ext = info.get("ext", "")

            # Reject unsupported formats
            if not stream_url or ext in ("webm", "opus"):
                return jsonify({"error": "Unsupported stream"}), 415

            return jsonify({
                "stream_url": stream_url,
                "ext": ext
            })

    except Exception:
        return jsonify({"error": "Playback unavailable"}), 500

# -------- LIBRARY --------

@app.route("/api/library")
@login_required
def library():
    likes = LikedTrack.query.filter_by(user_id=current_user.id).all()
    return jsonify([
        {
            "id": l.track_id,
            "title": l.title,
            "artist": l.artist,
            "thumbnail": l.thumbnail
        } for l in likes
    ])

@app.route("/api/like", methods=["POST"])
@login_required
def toggle_like():
    data = request.json

    existing = LikedTrack.query.filter_by(
        user_id=current_user.id,
        track_id=data["id"]
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "unliked"})

    like = LikedTrack(
        track_id=data["id"],
        title=data["title"],
        artist=data["artist"],
        thumbnail=data["thumbnail"],
        user_id=current_user.id
    )

    db.session.add(like)
    db.session.commit()

    return jsonify({"status": "liked"})

# ---------------- START SERVER ----------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
