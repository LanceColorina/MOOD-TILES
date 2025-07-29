"""
Database models for Spotify Mood Tracker with User Mood Customization
"""
import os
import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from cryptography.fernet import Fernet
import base64

# --- Database Setup ---
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# --- Encryption Setup for Tokens ---
def get_cipher_suite():
    """Get or create cipher suite for token encryption"""
    encryption_key = os.getenv('ENCRYPTION_KEY')
    if not encryption_key:
        # Generate a new key if none exists (for development)
        encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        print(f"Generated new encryption key: {encryption_key}")
        print("Add this to your .env file as ENCRYPTION_KEY=")
    
    return Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)

def encrypt_token(token):
    """Encrypt a token for secure storage"""
    if token:
        cipher_suite = get_cipher_suite()
        return cipher_suite.encrypt(token.encode()).decode()
    return None

def decrypt_token(encrypted_token):
    """Decrypt a token for use"""
    if encrypted_token:
        cipher_suite = get_cipher_suite()
        return cipher_suite.decrypt(encrypted_token.encode()).decode()
    return None

# --- Database Models ---
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(100), unique=True, nullable=False)
    access_token = db.Column(db.Text, nullable=True)  # Encrypted
    refresh_token = db.Column(db.Text, nullable=True)  # Encrypted
    token_expires_at = db.Column(db.DateTime, nullable=True)
    mood_overrides = db.Column(db.Text, nullable=True)  # JSON string of custom moods
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to listens
    listens = db.relationship('Listen', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_tokens(self, access_token, refresh_token, expires_at):
        """Encrypt and store tokens"""
        self.access_token = encrypt_token(access_token)
        self.refresh_token = encrypt_token(refresh_token)
        self.token_expires_at = expires_at
        self.last_updated = datetime.utcnow()
    
    def get_access_token(self):
        """Get decrypted access token"""
        return decrypt_token(self.access_token)
    
    def get_refresh_token(self):
        """Get decrypted refresh token"""
        return decrypt_token(self.refresh_token)
    
    def is_token_expired(self):
        """Check if token is expired"""
        if not self.token_expires_at:
            return True
        return datetime.utcnow() >= self.token_expires_at
    
    def get_mood_overrides(self):
        """Get user's mood overrides as dictionary"""
        if self.mood_overrides:
            try:
                return json.loads(self.mood_overrides)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_mood_override(self, track_id, mood):
        """Set custom mood for a specific track"""
        overrides = self.get_mood_overrides()
        overrides[str(track_id)] = mood
        self.mood_overrides = json.dumps(overrides)
        db.session.commit()
    
    def remove_mood_override(self, track_id):
        """Remove custom mood override for a track"""
        overrides = self.get_mood_overrides()
        if str(track_id) in overrides:
            del overrides[str(track_id)]
            self.mood_overrides = json.dumps(overrides) if overrides else None
            db.session.commit()
    
    def get_track_mood(self, track):
        """Get mood for a track (custom override or default)"""
        overrides = self.get_mood_overrides()
        track_id_str = str(track.id)
        
        # Return custom mood if exists, otherwise return track's default mood
        return overrides.get(track_id_str, track.mood)
    
    def __repr__(self):
        return f'<User {self.spotify_id}>'

class Track(db.Model):
    __tablename__ = 'tracks'
    
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    deezer_id = db.Column(db.BigInteger, nullable=True)
    gain = db.Column(db.Float, nullable=True)
    mood = db.Column(db.String(50), nullable=True)  # Default mood from Deezer analysis
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to listens
    listens = db.relationship('Listen', backref='track', lazy=True)
    
    def __repr__(self):
        return f'<Track {self.name} by {self.artist}>'

class Listen(db.Model):
    __tablename__ = 'listens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    track_id = db.Column(db.Integer, db.ForeignKey('tracks.id'), nullable=False)
    played_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add a unique constraint to prevent duplicate listens
    __table_args__ = (db.UniqueConstraint('user_id', 'track_id', 'played_at', name='unique_listen'),)
    
    def get_mood_for_user(self, user):
        """Get the mood for this listen considering user's custom overrides"""
        return user.get_track_mood(self.track)
    
    def __repr__(self):
        return f'<Listen user_id={self.user_id} track_id={self.track_id} at {self.played_at}>'