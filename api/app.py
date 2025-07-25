import os
import secrets
from flask import Flask, redirect, request, session, render_template
from flask_session import Session
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime
import calendar

# Import our custom modules
from api.models import db, User, Track, Listen
from api.database import save_listening_history, get_user_recent_listens, get_monthly_listens, get_user_stats
from api.auth import create_or_update_user, login_required

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
    scope="user-read-recently-played",
    cache_path=None
)

# Create the login_required decorator with our sp_oauth instance
login_required = login_required(sp_oauth)

# --- Routes ---
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login():
    session.clear()
    session['nonce'] = secrets.token_hex(16)
    return redirect(sp_oauth.get_authorize_url())

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

        return redirect('/recent')
    except Exception as e:
        session.clear()
        print("Callback error:", e)
        return redirect('/login')

@app.route('/recent')
@login_required
def recent(sp, user):
    try:
        # Fetch recent songs from Spotify and save to database
        results = sp.current_user_recently_played(limit=50)
        save_listening_history(user, results['items'])
        
        # Get recent listens from database for display
        recent_listens = get_user_recent_listens(user, limit=10)
        
        songs = []
        for listen, track in recent_listens:
            songs.append({
                'name': track.name,
                'artist': track.artist,
                'mood': track.mood,
                'played_at': listen.played_at.strftime('%B %d, %Y, %I:%M %p')
            })
        
        # Pagination
        page = int(request.args.get('page', 1))
        per_page = 5
        total_pages = (len(songs) + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        paginated_songs = songs[start:end]

        return render_template('home.html', songs=paginated_songs, page=page, total_pages=total_pages)
    except Exception as e:
        print("Error fetching recent tracks:", e)
        import traceback; traceback.print_exc()
        return redirect('/login')

@app.route('/monthly', methods=['GET', 'POST'])
@login_required
def monthly(sp, user):
    if request.method == 'POST':
        selected_month = request.form['month']  # Format: YYYY-MM
        try:
            year, month = map(int, selected_month.split('-'))
            
            # Query database for listens in the selected month (super fast!)
            monthly_listens = get_monthly_listens(user, year, month)
            
            # Group by day
            daily_moods = defaultdict(list)
            for listen, track in monthly_listens:
                day_key = listen.played_at.strftime('%Y-%m-%d')
                mood = track.mood
                daily_moods[day_key].append(mood)
            
            # Create mood grid
            num_days = calendar.monthrange(year, month)[1]
            month_days = [datetime(year, month, d).strftime('%Y-%m-%d') for d in range(1, num_days + 1)]
            
            mood_grid = []
            for day in month_days:
                moods = daily_moods.get(day, [])
                if moods:
                    # Find most common mood
                    dominant = max(moods, key=moods.count)
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

@app.route('/stats')
@login_required
def stats(sp, user):
    """Display user statistics"""
    try:
        user_stats = get_user_stats(user)
        
        return render_template('stats.html',
            total_listens=user_stats['total_listens'],
            unique_tracks=user_stats['unique_tracks'],
            mood_stats=user_stats['mood_stats'],
            recent_activity=user_stats['recent_activity']
        )
    except Exception as e:
        print("Error generating stats:", e)
        return redirect('/login')

@app.route('/logout')
def logout():
    """Log out user"""
    session.clear()
    return redirect('/')

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