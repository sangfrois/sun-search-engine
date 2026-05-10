import urllib.parse
import re
import concurrent.futures
from functools import lru_cache
from flask import Flask, request, render_template, jsonify, redirect
import requests
import sqlite3
import os
from functools import wraps

app = Flask(__name__)
USER = os.environ.get('SUN_USER', 'admin')
PASS = os.environ.get('SUN_PASS', 'admin')

def check_auth(username, password):
    return username == USER and password == PASS

def authenticate():
    return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def init_db():
    conn = sqlite3.connect('/app/data/sun_rl.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS preferences (word TEXT PRIMARY KEY, weight REAL)')
    conn.commit()
    conn.close()

init_db()

def get_weights():
    conn = sqlite3.connect('/app/data/sun_rl.db')
    c = conn.cursor()
    c.execute('SELECT word, weight FROM preferences')
    weights = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return weights

def update_weights(title):
    words = title.lower().split()
    conn = sqlite3.connect('/app/data/sun_rl.db')
    c = conn.cursor()
    for w in words:
        if len(w) > 3:
            c.execute('INSERT INTO preferences (word, weight) VALUES (?, 1.0) ON CONFLICT(word) DO UPDATE SET weight=weight+0.5', (w,))
    conn.commit()
    conn.close()

@app.route('/')
@requires_auth
def index():

    return render_template('index.html')

@app.route('/search')
@requires_auth
def search():
    q = request.args.get('q', '')
    if not q: return redirect('/')

    # Log query history
    conn = sqlite3.connect('/app/data/sun_rl.db')
    conn.execute('INSERT INTO history (query) VALUES (?)', (q,))
    conn.commit()
    conn.close()
    
    # Fetch from SearXNG internal container
    r = requests.get('http://searxng:8080/search', params={'q': q, 'format': 'json'})
    if r.status_code != 200:
        return "Search failed", 500
        
    data = r.json()
    results = data.get('results', [])
    
    # RL Re-ranking mechanism
    weights = get_weights()
    for res in results:
        score = res.get('score', 0)
        title_words = res.get('title', '').lower().split()
        rl_boost = sum(weights.get(w, 0) for w in title_words if len(w) > 3)
        res['rl_score'] = score + rl_boost
        
    results.sort(key=lambda x: x.get('rl_score', 0), reverse=True)
    
    # --- Usito French Definition Override ---
    q_lower = q.lower().strip()
    match = re.search(r'(?:d[eé]finition(?:s)?(?:\s+de)?\s+([a-zà-ÿ-]+))|(?:([a-zà-ÿ-]+)\s+d[eé]finition(?:s)?)', q_lower)
    
    if match:
        word_to_define = match.group(1) if match.group(1) else match.group(2)
        if word_to_define:
            usito_result = {
                'title': f'📖 Usito : Définition de "{word_to_define}"',
                'url': f'https://usito.usherbrooke.ca/définitions/{word_to_define}',
                'content': f'Dictionnaire en ligne Usito - Université de Sherbrooke. Consultez la définition officielle et sans traçage de "{word_to_define}".',
                'rl_score': float('inf')
            }
            results.insert(0, usito_result)
    


    # --- Bandcamp Music Override ---
    music_keywords = {'bandcamp', 'music', 'band', 'artist', 'album', 'song', 'ep', 'vinyl', 'musique', 'groupe', 'chanson', 'artiste'}
    query_words = set(q_lower.split())
    
    is_music_intent = bool(music_keywords.intersection(query_words))
    
    if not is_music_intent:
        music_domains = ['bandcamp.com', 'open.spotify.com', 'music.apple.com', 'last.fm', 'soundcloud.com', 'genius.com']
        top_urls = [res.get('url', '').lower() for res in results[:4]]
        is_music_intent = any(any(domain in url for domain in music_domains) for url in top_urls)

    if is_music_intent:
        bc_query = q.strip()
        bc_result = {
            'title': f'🎸 Bandcamp : Écouter et soutenir "{bc_query}"',
            'url': f'https://bandcamp.com/search?q={urllib.parse.quote(bc_query)}',
            'content': f'Contournez le streaming corporatif. Soutenez directement les créateurs en explorant leur musique sur Bandcamp.',
            'rl_score': float('inf')
        }
        results.insert(0, bc_result)

    return render_template('index.html', results=results, query=q)


@lru_cache(maxsize=500)
def fetch_external_autocomplete(q):
    try:
        proxies = {
            'http': 'socks5h://tor:9050',
            'https': 'socks5h://tor:9050'
        }
        # Aggressive 0.6s timeout so the UI never hangs.
        r = requests.get('https://duckduckgo.com/ac/', params={'q': q, 'type': 'list'}, proxies=proxies, timeout=0.6)
        if r.status_code == 200:
            return r.json()[1]
    except Exception:
        pass
    return []

def fetch_local_autocomplete(q):
    try:
        conn = sqlite3.connect('/app/data/sun_rl.db')
        c = conn.cursor()
        c.execute('SELECT word FROM preferences WHERE word LIKE ? ORDER BY weight DESC LIMIT 4', (q + '%',))
        rl_results = [row[0] for row in c.fetchall()]
        conn.close()
        return rl_results
    except Exception:
        return []

@app.route('/autocomplete')
@requires_auth
def autocomplete():
    q = request.args.get('q', '').lower()
    if not q: return jsonify([])
    
    suggestions = []
    
    # Run Local DB query and Tor Network query CONCURRENTLY
    with concurrent.futures.ThreadPoolExecutor() as executor:
        local_future = executor.submit(fetch_local_autocomplete, q)
        ext_future = executor.submit(fetch_external_autocomplete, q)
        
        rl_results = local_future.result()
        for res in rl_results:
            suggestions.append({"text": res, "source": "rl"})
            
        ext_results = ext_future.result()
        for res in ext_results:
            if not any(s['text'] == res for s in suggestions):
                suggestions.append({"text": res, "source": "general"})
                
    return jsonify(suggestions[:8])

@app.route('/click')



@requires_auth
def click():
    url = request.args.get('url')
    title = request.args.get('title', '')
    if url and title:
        update_weights(title)
    return redirect(url)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
