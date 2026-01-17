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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- AUTH ROUTES ----------------
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json
    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "User exists"}), 400
    user = User(username=data["username"], password=generate_password_hash(data["password"]))
    db.session.add(user)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data["username"]).first()
    if user and check_password_hash(user.password, data["password"]):
        login_user(user, remember=True)
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
@app.route("/api/search")
@login_required
def search():
    q = request.args.get("q")
    if not q: return jsonify([])
    
    ydl_opts = {"quiet": True, "extract_flat": True, "noplaylist": True, "http_headers": HEADERS}
    with YoutubeDL(ydl_opts) as ydl:
        data = ydl.extract_info(f"scsearch20:{q}", download=False)
        results = []
        for e in data.get("entries", []):
            if e:
                results.append({
                    "id": e.get("url"),
                    "title": e.get("title"),
                    "artist": e.get("uploader") or "SoundCloud Artist",
                    "thumbnail": e.get("thumbnail") or "https://placehold.co/100x100"
                })
        return jsonify(results)

@app.route("/api/play", methods=["POST"])
@login_required
def play():
    url = request.json.get("url")
    try:
        ydl_opts = {"format": "bestaudio", "quiet": True, "http_headers": HEADERS}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({"stream_url": info["url"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
