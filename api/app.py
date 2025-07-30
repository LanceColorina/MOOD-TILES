import os
import secrets
from flask import Flask, redirect, request, session, render_template, jsonify
from flask_session import Session
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import calendar
from flask import url_for
from flask import make_response

# Import our custom modules
from .models import db, User, Track, Listen
from .database import (
    get_or_create_track, save_listening_history, 
    get_user_recent_listens_with_moods, get_monthly_listens_with_moods, 
    get_user_stats_with_custom_moods, update_user_mood_override, get_available_moods
)
from .auth import create_or_update_user, login_required

# --- Load environment variables ---
load_dotenv()

# --- Flask App Setup ---
app = Flask(__name__, static_folder='../static', template_folder='../templates')

# --- Database Configuration ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///spotify_mood.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# --- Session Configuration ---
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

# --- Spotify OAuth Setup ---
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="user-read-recently-played user-read-playback-state user-read-currently-playing",
    show_dialog=True
)

# Create the login_required decorator with our sp_oauth instance
login_required = login_required(sp_oauth)

# --- Helper function for timezone conversion ---
def to_manila_time(utc_datetime):
    """Convert UTC datetime to Manila timezone"""
    manila_tz = timezone(timedelta(hours=8))  # UTC+8 for Manila
    return utc_datetime.replace(tzinfo=timezone.utc).astimezone(manila_tz)

# --- Routes ---
@app.route('/')
def index():
    if 'token_info' in session and 'user_id' in session:
        return redirect('/recent')
    return render_template('login.html', sp_oauth=sp_oauth)

@app.route('/login')
def login():
    session.clear()  
    # Only generate nonce, don't clear session unless needed
    if 'user_id' in session and 'token_info' in session:
        return redirect('/recent')  # Already logged in
    session['nonce'] = secrets.token_hex(16)
    return render_template('login.html', sp_oauth=sp_oauth)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        print("Spotify returned an error:", error)
        return redirect('/login')

    try:
        # Get token and user info from Spotify
        token_info = sp_oauth.get_access_token(code)
        session['token_info'] = token_info

        from spotipy import Spotify
        sp = Spotify(auth=token_info['access_token'])
        user_info = sp.current_user()
        
        # Create or update user in database
        user = create_or_update_user(user_info, token_info)
        session['user_id'] = user.id
        session['logged_in'] = True
        session['show_about_modal'] = True

        return redirect('/recent')
    except Exception as e:
        session.clear()
        print("Callback error:", e)
        return redirect('/login')

@app.route('/recent')
@login_required
def recent(sp, user):
    try:
        
        # Get currently playing track
        current_song = None
        show_modal = session.pop('show_about_modal', False)
        try:
            current_playing = sp.current_playbook()
            if current_playing and current_playing.get('is_playing'):
                track_data = current_playing['item']
                db_track = get_or_create_track(track_data)
                mood = user.get_track_mood(db_track)  # Get user's custom mood or default
                current_song = {
                    'name': track_data['name'],
                    'artist': ', '.join([a['name'] for a in track_data['artists']]),
                    'mood': mood,
                    'image': track_data['album']['images'][0]['url'] if track_data['album']['images'] else None,
                    'url': track_data['external_urls']['spotify'],
                    'track_id': db_track.id
                }
        except Exception as e:
            print("Warning: Failed to fetch current playing track.", e)

        # Save recent listens to DB
        results = sp.current_user_recently_played(limit=50)
        save_listening_history(user, results['items'])

        # Retrieve recent listens from DB with custom moods
        recent_listens = get_user_recent_listens_with_moods(user, limit=15)

        songs = []
        for listen_data in recent_listens:
            listen = listen_data['listen']
            track = listen_data['track']
            mood = listen_data['mood']
            is_custom = listen_data['is_custom_mood']
            
            local_time = to_manila_time(listen.played_at)
            songs.append({
                'track_id': track.id,
                'name': track.name,
                'artist': track.artist,
                'mood': mood,
                'is_custom_mood': is_custom,
                'url': f"https://open.spotify.com/track/{track.spotify_id}",  
                'played_at': local_time.strftime('%B %d, %Y, %I:%M %p')
            })

        # Pagination
        page = int(request.args.get('page', 1))
        per_page = 5
        total_pages = (len(songs) + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        paginated_songs = songs[start:end]

        # Get available moods for dropdown
        available_moods = get_available_moods()

        return render_template(
            'home.html',
            songs=paginated_songs,
            page=page,
            total_pages=total_pages,
            current_song=current_song,
            show_modal=show_modal,
            available_moods=available_moods
        )

    except Exception as e:
        print("Error fetching recent tracks:", e)
        import traceback
        traceback.print_exc()
        return redirect('/login')

@app.route('/update-mood', methods=['POST'])
@login_required
def update_mood(sp, user):
    """Update user's custom mood for a track"""
    try:
        data = request.get_json()
        track_id = data.get('track_id')
        new_mood = data.get('mood')
        
        if not track_id or not new_mood:
            return jsonify({'success': False, 'error': 'Missing track_id or mood'}), 400
        
        success = update_user_mood_override(user, track_id, new_mood)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Invalid mood or track'}), 400
            
    except Exception as e:
        print("Error updating mood:", e)
        return jsonify({'success': False, 'error': 'Server error'}), 500

@app.route('/monthly', methods=['GET', 'POST'])
@login_required
def monthly(sp, user):
    if request.method == 'POST':
        selected_month = request.form['month']  # Format: YYYY-MM
        try:
            year, month = map(int, selected_month.split('-'))
            
            # Query database for listens in the selected month with custom moods
            monthly_listens = get_monthly_listens_with_moods(user, year, month)
            
            # Group by day
            daily_moods = defaultdict(list)
            for listen_data in monthly_listens:
                listen = listen_data['listen']
                mood = listen_data['mood']
                day_key = listen.played_at.strftime('%Y-%m-%d')
                daily_moods[day_key].append(mood)
            
            # Create mood grid
            num_days = calendar.monthrange(year, month)[1]
            month_days = [datetime(year, month, d).strftime('%Y-%m-%d') for d in range(1, num_days + 1)]
            
            mood_grid = []
            for day in month_days:
                moods = daily_moods.get(day, [])
                if moods:
                    mood_scores = {
                        'Angry 😠': 5,
                        'Energetic 🔥': 4,
                        'Happy 😊': 3,
                        'Chill 😎': 2,
                        'Calm 🧘': 1,
                        'Sad 😢': 0,
                        'Depressed 😞': -1,
                        'Unknown 🤷': 2.5
                    }
                    # Average mood score for the day
                    valid_moods = [m for m in moods if m in mood_scores]
                    if valid_moods:
                        avg_score = sum(mood_scores[m] for m in valid_moods) / len(valid_moods)
                        # Find the mood with closest score
                        dominant = min(mood_scores.keys(), key=lambda m: abs(mood_scores[m] - avg_score))
                    else:
                        dominant = 'Unknown 🤷'
                else:
                    dominant = 'No Data 📭'
                mood_grid.append({'day': day, 'mood': dominant, 'count': len(moods)})

            return render_template(
                'monthly.html',
                mood_grid=mood_grid,
                month=selected_month,
                year=year,
                month_name=calendar.month_name[month],
                datetime=datetime
            )
        except Exception as e:
            print("Error generating mood grid:", e)
            import traceback; traceback.print_exc()
            return redirect('/login')

    return render_template('month_form.html')

@app.route('/api/day-songs')
@login_required
def day_songs(sp, user):
    date_str = request.args.get('date')
    if not date_str:
        return {"error": "Missing date"}, 400

    try:
        # Parse date
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = start + timedelta(days=1)

        listens = Listen.query.filter(
            Listen.user_id == user.id,
            Listen.played_at >= start,
            Listen.played_at < end
        ).order_by(Listen.played_at).all()

        results = []
        available_moods = get_available_moods()

        for listen in listens:
            track = Track.query.get(listen.track_id)
            if not track:
                continue

            local_time = to_manila_time(listen.played_at)
            mood = user.get_track_mood(track)  # Get custom or default mood
            is_custom = str(track.id) in user.get_mood_overrides()
            
            results.append({
                "track_id": track.id,
                "name": track.name,
                "artist": track.artist,
                "mood": mood,
                "is_custom_mood": is_custom,
                'url': f"https://open.spotify.com/track/{track.spotify_id}",
                "played_at": local_time.strftime('%I:%M %p'),
                "available_moods": available_moods
            })

        return jsonify(results)

    except Exception as e:
        print("Error fetching day songs:", e)
        return {"error": "Internal server error"}, 500

@app.route('/stats')
@login_required
def stats(sp, user):
    """Display user statistics with custom moods considered"""
    try:
        user_stats = get_user_stats_with_custom_moods(user)
        
        return render_template('stats.html',
            total_listens=user_stats['total_listens'],
            unique_tracks=user_stats['unique_tracks'],
            mood_stats=user_stats['mood_stats'],
            recent_activity=user_stats['recent_activity'],
            custom_mood_overrides=user_stats['custom_mood_overrides']
        )
    except Exception as e:
        print("Error generating stats:", e)
        return redirect('/login')

@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    
    # Expire session cookie explicitly
    response = make_response(redirect('/login'))
    response.set_cookie('session', '', expires=0)

    print("Session cleared.")
    return response

# --- Initialize Database ---
@app.before_request
def create_tables():
    """Create database tables on first request"""
    db.create_all()

if __name__ == '__main__':
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
        print("Database tables created!")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)