import os
import secrets
from flask import Flask, redirect, request, session, render_template
from flask_session import Session
import redis
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime
from functools import wraps
import calendar

load_dotenv()

# --- Flask App Setup ---
app = Flask(__name__, static_folder='../static', template_folder='../templates')

# --- Redis Session Configuration ---
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url(os.getenv("REDIS_URL"))
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)

# --- Spotify OAuth Setup ---
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="user-read-recently-played",
    cache_path=None
)

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
    token_info = sp_oauth.get_access_token(code, as_dict=True)
    session['token_info'] = token_info  # 🔐 store token in session

    sp = Spotify(auth=token_info['access_token'])
    user = sp.current_user()
    session['user_id'] = user['id']  # 🔐 store user id in session

    return redirect('/recent')

def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        token_info = session.get('token_info')
        user_id = session.get('user_id')
        if not token_info or not user_id:
            return redirect('/login')
        try:
            sp = Spotify(auth=token_info['access_token'])
            current_user = sp.current_user()
            if current_user['id'] != user_id:
                session.clear()
                return redirect('/login')
            return view_func(sp, *args, **kwargs)
        except Exception:
            session.clear()
            return redirect('/login')
    return wrapper

@app.route('/recent')
@login_required
def recent(sp):
    print("📌 Showing recent for user:", session.get('user_id'))
    results = sp.current_user_recently_played(limit=10)
    songs = [{
        'name': item['track']['name'],
        'artist': item['track']['artists'][0]['name'],
        'played_at': item['played_at']
    } for item in results['items']]
    return render_template('home.html', songs=songs)

@app.route('/monthly', methods=['GET', 'POST'])
@login_required
def monthly(sp):
    if request.method == 'POST':
        selected_month = request.form['month']  # YYYY-MM
        results = sp.current_user_recently_played(limit=50)
        year, month = map(int, selected_month.split('-'))
        num_days = calendar.monthrange(year, month)[1]
        month_days = [datetime(year, month, d).strftime('%Y-%m-%d') for d in range(1, num_days + 1)]

        daily_moods = defaultdict(list)
        for item in results['items']:
            dt = datetime.fromisoformat(item['played_at'].replace('Z', '+00:00'))
            if dt.strftime('%Y-%m') == selected_month:
                mood = classify_mood(item['track'])
                daily_moods[dt.strftime('%Y-%m-%d')].append(mood)

        mood_grid = []
        for day in month_days:
            moods = daily_moods.get(day, [])
            dominant = max(moods, key=moods.count) if moods else 'Unknown 😐'
            mood_grid.append({'day': day, 'mood': dominant})

        return render_template(
            'monthly.html',
            mood_grid=mood_grid,
            month=selected_month,
            year=year,
            month_name=calendar.month_name[month],
            datetime=datetime
        )
    return render_template('month_form.html')

def classify_mood(track):
    name = track['name'].lower()
    if any(w in name for w in ['happy', 'love', 'sunshine']):
        return 'Happy 😊'
    if any(w in name for w in ['sad', 'blue', 'tears']):
        return 'Sad 😢'
    if any(w in name for w in ['chill', 'calm', 'lofi']):
        return 'Relaxed 🧘'
    if any(w in name for w in ['fire', 'lit', 'hype']):
        return 'Energetic 🔥'
    return 'Neutral 😐'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


