import os
from flask import Flask, redirect, request, session, url_for, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

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
    return redirect(sp_oauth.get_authorize_url())

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code, as_dict=True)
    session['token_info'] = token_info
    return redirect('/recent')

@app.route('/recent')
def recent():
    token_info = session.get('token_info')
    if not token_info:
        return redirect('/login')

    sp = Spotify(auth=token_info['access_token'])
    results = sp.current_user_recently_played(limit=10)

    songs = []
    for item in results['items']:
        track = item['track']
        songs.append({
            'name': track['name'],
            'artist': track['artists'][0]['name'],
            'played_at': item['played_at']
        })

    return render_template('home.html', songs=songs)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))  # Render gives PORT env var
    app.run(host='0.0.0.0', port=port, debug=False)

