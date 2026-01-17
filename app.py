import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import yt_dlp

# --- CHANGE: Set template folder to root ('.') ---
app = Flask(__name__, template_folder='.')

# --- Configuration ---
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "vofo_premium_secret_99")
db_url = os.environ.get("DATABASE_URL", "sqlite:///vofo.db")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'index'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    likes = db.relationship('LikedSong', backref='owner', lazy=True)

class LikedSong(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200))
    artist = db.Column(db.String(200))
    thumbnail = db.Column(db.String(500))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Auth Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/status')
def auth_status():
    if current_user.is_authenticated:
        return jsonify({"logged_in": True, "user": current_user.username})
    return jsonify({"logged_in": False})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Missing data"}), 400
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "Username taken"}), 400
    hashed_pw = generate_password_hash(data['password'], method='pbkdf2:sha256')
    new_user = User(username=data['username'], password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return jsonify({"success": True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password, data['password']):
        login_user(user, remember=True)
        return jsonify({"success": True})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- Music Engine ---
@app.route('/api/search')
@login_required
def search():
    q = request.args.get('q')
    if not q: return jsonify([])
    ydl_opts = {'format': 'bestaudio', 'noplaylist': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch10:{q}", download=False)['entries']
            return jsonify([{
                'id': v['id'], 'title': v.get('title', 'Unknown'),
                'artist': v.get('uploader', 'Artist'), 'thumbnail': v.get('thumbnail')
            } for v in info])
        except: return jsonify([])

@app.route('/api/play', methods=['POST'])
@login_required
def play():
    video_id = request.json.get('url')
    ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        return jsonify({"stream_url": info['url']})

@app.route('/api/like', methods=['POST'])
@login_required
def toggle_like():
    data = request.json
    existing = LikedSong.query.filter_by(user_id=current_user.id, video_id=data['id']).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "unliked"})
    new_like = LikedSong(user_id=current_user.id, video_id=data['id'], title=data['title'], artist=data['artist'], thumbnail=data['thumbnail'])
    db.session.add(new_like)
    db.session.commit()
    return jsonify({"status": "liked"})

@app.route('/api/library')
@login_required
def get_library():
    songs = LikedSong.query.filter_by(user_id=current_user.id).all()
    return jsonify([{'id': s.video_id, 'title': s.title, 'artist': s.artist, 'thumbnail': s.thumbnail} for s in songs])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
