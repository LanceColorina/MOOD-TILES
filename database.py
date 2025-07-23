"""
Database helper functions for Spotify Mood Tracker
"""
import requests
from datetime import datetime
from models import db, User, Track, Listen

def get_deezer_id(name, artist):
    """Get Deezer track ID for a song"""
    try:
        q = f"{name} {artist}"
        r = requests.get("https://api.deezer.com/search", params={"q": q}, timeout=10)
        r.raise_for_status()
        results = r.json()["data"]
        if results:
            return results[0]["id"]
        return None
    except Exception as e:
        print(f"Error getting Deezer ID for {name} by {artist}: {e}")
        return None

def get_deezer_metrics(deezer_id):
    """Get audio metrics from Deezer API"""
    try:
        url = f"https://api.deezer.com/track/{deezer_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "bpm": data.get("bpm"),
            "gain": data.get("gain"),
            "isrc": data.get("isrc"),
            "preview_url": data.get("preview")
        }
    except Exception as e:
        print(f"Error getting Deezer metrics for ID {deezer_id}: {e}")
        return {}

def classify_mood(track_metrics):
    """Classify mood based on track metrics"""
    gain = track_metrics.get('gain')
    if gain is None:
        return 'Unknown 🤷'
    if gain > 3:
        return 'Angry 😠'
    elif gain > 0:
        return 'Energetic 🔥'
    elif gain > -2:
        return 'Happy 😊'
    elif gain > -6:
        return 'Chill 😎'
    elif gain > -10:
        return 'Calm 🧘'
    elif gain > -14:
        return 'Sad 😢'
    else:
        return 'Depressed 😞'

def get_or_create_track(spotify_track):
    """
    Get existing track or create new one with mood analysis
    
    Args:
        spotify_track: Track data from Spotify API
        
    Returns:
        Track: Database track object
    """
    spotify_id = spotify_track['id']
    
    # Check if track already exists
    track = Track.query.filter_by(spotify_id=spotify_id).first()
    
    if track:
        return track
    
    # Create new track
    track = Track(
        spotify_id=spotify_id,
        name=spotify_track['name'],
        artist=spotify_track['artists'][0]['name']
    )
    
    # Analyze mood
    try:
        deezer_id = get_deezer_id(track.name, track.artist)
        if deezer_id:
            track.deezer_id = deezer_id
            metrics = get_deezer_metrics(deezer_id)
            track.gain = metrics.get('gain')
            track.mood = classify_mood(metrics)
        else:
            track.mood = 'Unknown 🤷'
    except Exception as e:
        print(f"Error analyzing track {track.name}: {e}")
        track.mood = 'Unknown 🤷'
    
    db.session.add(track)
    db.session.commit()
    return track

def save_listening_history(user, spotify_items):
    """
    Save listening history from Spotify API to database
    
    Args:
        user: User database object
        spotify_items: List of recently played items from Spotify API
        
    Returns:
        int: Number of new listening records saved
    """
    saved_count = 0
    
    for item in spotify_items:
        played_at_str = item['played_at']
        played_at = datetime.fromisoformat(played_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
        
        # Get or create track
        track = get_or_create_track(item['track'])
        
        # Check if listen already exists
        existing_listen = Listen.query.filter_by(
            user_id=user.id,
            track_id=track.id,
            played_at=played_at
        ).first()
        
        if not existing_listen:
            listen = Listen(
                user_id=user.id,
                track_id=track.id,
                played_at=played_at
            )
            db.session.add(listen)
            saved_count += 1
    
    if saved_count > 0:
        db.session.commit()
        print(f"Saved {saved_count} new listening records")
    
    return saved_count

def get_user_recent_listens(user, limit=10):
    """
    Get recent listening history for a user from database
    
    Args:
        user: User database object
        limit: Maximum number of listens to return
        
    Returns:
        list: List of (Listen, Track) tuples
    """
    return db.session.query(Listen, Track).join(Track).filter(
        Listen.user_id == user.id
    ).order_by(Listen.played_at.desc()).limit(limit).all()

def get_monthly_listens(user, year, month):
    """
    Get all listens for a user in a specific month
    
    Args:
        user: User database object
        year: Year (int)
        month: Month (int, 1-12)
        
    Returns:
        list: List of (Listen, Track) tuples for the month
    """
    # Create date range for the month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    return db.session.query(Listen, Track).join(Track).filter(
        Listen.user_id == user.id,
        Listen.played_at >= start_date,
        Listen.played_at < end_date
    ).all()

def get_user_stats(user):
    """
    Get statistics for a user
    
    Args:
        user: User database object
        
    Returns:
        dict: Dictionary containing user statistics
    """
    from datetime import timedelta
    
    # Total listens
    total_listens = Listen.query.filter_by(user_id=user.id).count()
    
    # Unique tracks
    unique_tracks = db.session.query(Track.id).join(Listen).filter(
        Listen.user_id == user.id
    ).distinct().count()
    
    # Mood distribution
    mood_stats = db.session.query(Track.mood, db.func.count(Listen.id)).join(Listen).filter(
        Listen.user_id == user.id,
        Track.mood.isnot(None)
    ).group_by(Track.mood).all()
    
    # Recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_activity = Listen.query.filter(
        Listen.user_id == user.id,
        Listen.played_at >= week_ago
    ).count()
    
    return {
        'total_listens': total_listens,
        'unique_tracks': unique_tracks,
        'mood_stats': mood_stats,
        'recent_activity': recent_activity
    }