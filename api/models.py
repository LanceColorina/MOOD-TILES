"""
Database models for Spotify Mood Tracker
"""
import os
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
    
    id = db.Column(db.String, primary_key=True)
    spotify_id = db.Column(db.String(100), unique=True, nullable=False)
    access_token = db.Column(db.Text, nullable=True)  # Encrypted
    refresh_token = db.Column(db.Text, nullable=True)  # Encrypted
    token_expires_at = db.Column(db.DateTime, nullable=True)
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
    mood = db.Column(db.String(50), nullable=True)
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
    
    def __repr__(self):
        return f'<Listen user_id={self.user_id} track_id={self.track_id} at {self.played_at}>'