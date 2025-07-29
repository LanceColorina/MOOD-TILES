"""
Database helper functions for Spotify Mood Tracker with User Mood Customization
"""
import requests
from datetime import datetime
from .models import db, User, Track, Listen

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

def get_available_moods():
    """Get list of available mood options for dropdown"""
    return [
        'Angry 😠',
        'Energetic 🔥', 
        'Happy 😊',
        'Chill 😎',
        'Calm 🧘',
        'Sad 😢',
        'Depressed 😞'
    ]

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
    
    # Analyze mood (this becomes the default mood)
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

def update_user_mood_override(user, track_id, new_mood):
    """
    Update user's custom mood for a specific track
    
    Args:
        user: User database object
        track_id: Track ID to update mood for
        new_mood: New mood string
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Validate mood
        available_moods = get_available_moods()
        if new_mood not in available_moods:
            return False
        
        # Check if track exists
        track = Track.query.get(track_id)
        if not track:
            return False
        
        # If new mood matches the track's default mood, remove override
        if new_mood == track.mood:
            user.remove_mood_override(track_id)
        else:
            user.set_mood_override(track_id, new_mood)
        
        return True
    except Exception as e:
        print(f"Error updating mood override: {e}")
        return False

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

def get_user_recent_listens_with_moods(user, limit=10):
    """
    Get recent listening history for a user with their custom moods
    
    Args:
        user: User database object
        limit: Maximum number of listens to return
        
    Returns:
        list: List of dictionaries with listen, track, and mood info
    """
    listens_tracks = db.session.query(Listen, Track).join(Track).filter(
        Listen.user_id == user.id
    ).order_by(Listen.played_at.desc()).limit(limit).all()
    
    result = []
    for listen, track in listens_tracks:
        result.append({
            'listen': listen,
            'track': track,
            'mood': user.get_track_mood(track),  # This will get custom or default mood
            'is_custom_mood': str(track.id) in user.get_mood_overrides()
        })
    
    return result

def get_monthly_listens_with_moods(user, year, month):
    """
    Get all listens for a user in a specific month with their custom moods
    
    Args:
        user: User database object
        year: Year (int)
        month: Month (int, 1-12)
        
    Returns:
        list: List of dictionaries with listen, track, and mood info
    """
    # Create date range for the month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    listens_tracks = db.session.query(Listen, Track).join(Track).filter(
        Listen.user_id == user.id,
        Listen.played_at >= start_date,
        Listen.played_at < end_date
    ).all()
    
    result = []
    for listen, track in listens_tracks:
        result.append({
            'listen': listen,
            'track': track,
            'mood': user.get_track_mood(track),
            'is_custom_mood': str(track.id) in user.get_mood_overrides()
        })
    
    return result

def get_user_stats_with_custom_moods(user):
    """
    Get statistics for a user considering their custom mood overrides
    
    Args:
        user: User database object
        
    Returns:
        dict: Dictionary containing user statistics with custom moods
    """
    from datetime import timedelta
    from collections import defaultdict
    
    # Total listens
    total_listens = Listen.query.filter_by(user_id=user.id).count()
    
    # Unique tracks
    unique_tracks = db.session.query(Track.id).join(Listen).filter(
        Listen.user_id == user.id
    ).distinct().count()
    
    # Mood distribution with custom overrides
    listens_tracks = db.session.query(Listen, Track).join(Track).filter(
        Listen.user_id == user.id
    ).all()
    
    mood_counts = defaultdict(int)
    for listen, track in listens_tracks:
        mood = user.get_track_mood(track)  # Gets custom or default mood
        if mood:
            mood_counts[mood] += 1
    
    mood_stats = list(mood_counts.items())
    
    # Recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_activity = Listen.query.filter(
        Listen.user_id == user.id,
        Listen.played_at >= week_ago
    ).count()
    
    # Custom mood override count
    custom_mood_count = len(user.get_mood_overrides())
    
    return {
        'total_listens': total_listens,
        'unique_tracks': unique_tracks,
        'mood_stats': mood_stats,
        'recent_activity': recent_activity,
        'custom_mood_overrides': custom_mood_count
    }