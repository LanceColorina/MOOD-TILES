"""
Authentication helper functions for Spotify Mood Tracker
"""
from functools import wraps
from datetime import datetime, timedelta
from flask import session, redirect
from spotipy import Spotify
from .models import db, User

def create_or_update_user(spotify_user_info, token_info):
    """
    Create a new user or update existing user with token info
    
    Args:
        spotify_user_info: User info from Spotify API
        token_info: Token info from Spotify OAuth
        
    Returns:
        User: Database user object
    """
    spotify_id = spotify_user_info['id']
    
    # Get or create user in database
    user = User.query.filter_by(spotify_id=spotify_id).first()
    if not user:
        user = User(spotify_id=spotify_id)
        db.session.add(user)
    
    # Update user tokens
    expires_at = datetime.utcnow() + timedelta(seconds=token_info.get('expires_in', 3600))
    user.set_tokens(
        access_token=token_info['access_token'],
        refresh_token=token_info['refresh_token'],
        expires_at=expires_at
    )
    
    db.session.commit()
    return user

def refresh_user_tokens(user, sp_oauth):
    """
    Refresh expired tokens for a user
    
    Args:
        user: User database object
        sp_oauth: SpotifyOAuth object
        
    Returns:
        bool: True if refresh successful, False otherwise
    """
    try:
        refresh_token = user.get_refresh_token()
        if not refresh_token:
            return False
        
        token_info = sp_oauth.refresh_access_token(refresh_token)
        expires_at = datetime.utcnow() + timedelta(seconds=token_info.get('expires_in', 3600))
        user.set_tokens(
            access_token=token_info['access_token'],
            refresh_token=token_info['refresh_token'],
            expires_at=expires_at
        )
        db.session.commit()
        return True
        
    except Exception as e:
        print("Token refresh failed:", e)
        return False

def login_required(sp_oauth):
    """
    Decorator factory that creates a login_required decorator
    
    Args:
        sp_oauth: SpotifyOAuth object
        
    Returns:
        function: Decorator function
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user_id = session.get('user_id')
            
            if not user_id:
                return redirect('/login')
            
            # Get user from database
            user = User.query.get(user_id)
            if not user:
                session.clear()
                return redirect('/login')
            
            # Check if token needs refresh
            if user.is_token_expired():
                if not refresh_user_tokens(user, sp_oauth):
                    session.clear()
                    return redirect('/login')
            
            # Create Spotify client
            try:
                sp = Spotify(auth=user.get_access_token())
                return view_func(sp, user, *args, **kwargs)
            except Exception as e:
                session.clear()
                print("Spotify API error:", e)
                return redirect('/login')
        
        return wrapper
    return decorator