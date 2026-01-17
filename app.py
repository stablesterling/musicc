from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from yt_dlp import YoutubeDL
import os

app = Flask(__name__, static_folder=".", static_url_path="")
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "vofo-secret-123")
# Uses SQLite locally, but will use Postgres on Render if DATABASE_URL is set
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///vofo.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
CORS(app)

# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    likes = db.relationship('LikedSong', backref='user', lazy=True)

class LikedSong(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    artist = db.Column(db.String(100))
    thumbnail = db.Column(db.String(500))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- AUTH ROUTES ---
@app.route("/api/auth/status")
def auth_status():
    if current_user.is_authenticated:
        return jsonify({"logged_in": True, "username": current_user.username})
    return jsonify({"logged_in": False})

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "Username taken"}), 400
    hashed_pw = generate_password_hash(data['password'])
    new_user = User(username=data['username'], password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return jsonify({"message": "Registered successfully"})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password, data['password']):
        login_user(user, remember=True)
        return jsonify({"message": "Logged in"})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/logout")
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})

# --- LIKES ROUTES ---
@app.route("/api/like", methods=["POST"])
@login_required
def toggle_like():
    data = request.json
    existing = LikedSong.query.filter_by(user_id=current_user.id, track_id=data['id']).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "unliked"})
    
    new_like = LikedSong(
        track_id=data['id'], title=data['title'],
        artist=data['artist'], thumbnail=data['thumbnail'],
        user_id=current_user.id
    )
    db.session.add(new_like)
    db.session.commit()
    return jsonify({"status": "liked"})

@app.route("/api/my-likes")
@login_required
def get_likes():
    likes = LikedSong.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        "id": l.track_id, "title": l.title, "artist": l.artist, "thumbnail": l.thumbnail
    } for l in likes])

# --- MUSIC SEARCH/PLAY ---
HEADERS = {"User-Agent": "Mozilla/5.0"}

@app.route("/api/search")
def search():
    q = request.args.get("q")
    try:
        ydl_opts = {"quiet": True, "noplaylist": True, "extract_flat": True}
        with YoutubeDL(ydl_opts) as ydl:
            r = ydl.extract_info(f"scsearch10:{q}", download=False)
            results = [{
                "id": e.get("url"), "title": e.get("title"),
                "artist": e.get("uploader"), "thumbnail": e.get("thumbnail")
            } for e in r.get("entries", []) if e]
            return jsonify(results)
    except: return jsonify([])

@app.route("/api/play", methods=["POST"])
def play():
    track_url = request.json.get("url")
    try:
        ydl_opts = {"format": "bestaudio", "quiet": True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(track_url, download=False)
            return jsonify({"stream_url": info["url"]})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
