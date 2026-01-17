import os
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from yt_dlp import YoutubeDL

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# Configuration
app.config['SECRET_KEY'] = 'vofo_ultra_secret_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vofo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
port = int(os.environ.get("PORT", 5000))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    likes = db.relationship('LikedTrack', backref='user', lazy=True)

class LikedTrack(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    artist = db.Column(db.String(200))
    thumbnail = db.Column(db.String(500))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Auth Routes ---
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "User already exists"}), 400
    hashed_pw = generate_password_hash(data['password'], method='pbkdf2:sha256')
    new_user = User(username=data['username'], password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password, data['password']):
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

# --- Music & Search ---
def soundcloud_search(query):
    try:
        ydl_opts = {"quiet": True, "noplaylist": True, "extract_flat": True, "http_headers": HEADERS}
        with YoutubeDL(ydl_opts) as ydl:
            r = ydl.extract_info(f"scsearch10:{query}", download=False)
            results = []
            for e in r.get("entries", []):
                if not e: continue
                results.append({
                    "id": e.get("url"),
                    "title": e.get("title"),
                    "artist": e.get("uploader") or "SoundCloud Artist",
                    "thumbnail": e.get("thumbnail") or "https://placehold.co/50x50?text=No+Cover"
                })
            return results
    except: return []

@app.route("/api/search")
@login_required
def search():
    q = request.args.get("q")
    return jsonify(soundcloud_search(q)) if q else jsonify([])

@app.route("/api/play", methods=["POST"])
@login_required
def play():
    track_url = request.json.get("url")
    try:
        ydl_opts = {"format": "bestaudio", "quiet": True, "http_headers": HEADERS}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(track_url, download=False)
            return jsonify({"stream_url": info["url"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Likes Logic ---
@app.route("/api/library")
@login_required
def get_library():
    likes = LikedTrack.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        "id": l.track_id, "title": l.title, "artist": l.artist, "thumbnail": l.thumbnail
    } for l in likes])

@app.route("/api/like", methods=["POST"])
@login_required
def toggle_like():
    data = request.json
    existing = LikedTrack.query.filter_by(user_id=current_user.id, track_id=data['id']).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "unliked"})
    
    new_like = LikedTrack(
        track_id=data['id'], title=data['title'], artist=data['artist'],
        thumbnail=data['thumbnail'], user_id=current_user.id
    )
    db.session.add(new_like)
    db.session.commit()
    return jsonify({"status": "liked"})

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=port)
