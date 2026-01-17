import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from yt_dlp import YoutubeDL

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app, supports_credentials=True)

# ---------------- CONFIG ----------------
app.config["SECRET_KEY"] = "vofo_ultra_secret_2026"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///vofo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
}

# ---------------- DATABASE ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

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

# ---------------- AUTH ----------------
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json
    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "User exists"}), 400

    user = User(
        username=data["username"],
        password=generate_password_hash(data["password"])
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data["username"]).first()
    if user and check_password_hash(user.password, data["password"]):
        login_user(user)
        return jsonify({"success": True})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/auth/logout")
def logout():
    logout_user()
    return jsonify({"success": True})

@app.route("/api/auth/status")
def status():
    return jsonify({
        "logged_in": current_user.is_authenticated,
        "username": current_user.username if current_user.is_authenticated else None
    })

# ---------------- MUSIC SEARCH ----------------
def soundcloud_search(query):
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "noplaylist": True,
        "http_headers": HEADERS
    }
    with YoutubeDL(ydl_opts) as ydl:
        data = ydl.extract_info(f"scsearch20:{query}", download=False)
        results = []
        for e in data.get("entries", []):
            if not e:
                continue
            results.append({
                "id": e.get("url"),
                "title": e.get("title"),
                "artist": e.get("uploader") or "SoundCloud Artist",
                "thumbnail": e.get("thumbnail") or "https://placehold.co/100x100?text=No+Art"
            })
        return results

@app.route("/api/search")
@login_required
def search():
    q = request.args.get("q")
    return jsonify(soundcloud_search(q)) if q else jsonify([])

# ---------------- PLAY (FIXED: ALL SONGS PLAY) ----------------
@app.route("/api/play", methods=["POST"])
@login_required
def play():
    url = request.json.get("url")
    try:
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
            "quiet": True,
            "http_headers": HEADERS
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "stream_url": info["url"],
                "ext": info.get("ext")
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- LIKES ----------------
@app.route("/api/library")
@login_required
def library():
    tracks = LikedTrack.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        "id": t.track_id,
        "title": t.title,
        "artist": t.artist,
        "thumbnail": t.thumbnail
    } for t in tracks])

@app.route("/api/like", methods=["POST"])
@login_required
def like():
    data = request.json
    existing = LikedTrack.query.filter_by(
        user_id=current_user.id,
        track_id=data["id"]
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "unliked"})

    db.session.add(LikedTrack(
        track_id=data["id"],
        title=data["title"],
        artist=data["artist"],
        thumbnail=data["thumbnail"],
        user_id=current_user.id
    ))
    db.session.commit()
    return jsonify({"status": "liked"})

# ---------------- FRONTEND ----------------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
