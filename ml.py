import json
from functools import lru_cache
from pathlib import Path
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).parent

@lru_cache(maxsize=1)
def load_model():
    return joblib.load(ROOT/'models/sentiment.joblib')


def metrics():
    return json.loads((ROOT/'models/metrics.json').read_text())


def analyze(text):
    model = load_model()
    p = float(model.predict_proba([text])[0, 1])
    # Uncertain is an abstention band, NOT a neutral model class.
    label = 'Positive' if p >= .60 else 'Negative' if p <= .40 else 'Uncertain'
    return {'label': label, 'positive_probability': round(p, 4), 'negative_probability': round(1-p, 4),
            'model': 'TF-IDF + Logistic Regression', 'characters_analyzed': len(text)}


def aggregate(reviews):
    counts = {k: 0 for k in ('Positive', 'Uncertain', 'Negative')}
    for review in reviews:
        counts[review['sentiment']['label']] += 1
    n = len(reviews)
    return {'count': n, 'counts': counts, 'percentages': {k: round(v*100/n, 1) if n else 0 for k,v in counts.items()}}


def recommend(seeds, candidates, preferred_genres=(), exclude=(), limit=12):
    """Own content ranking over a live API candidate pool, not TMDB's ordering."""
    candidates = list({m['id']: m for m in candidates if m.get('id') not in exclude and not m.get('adult')}.values())
    if not candidates:
        return []
    def genre_ids(m):
        return set(m.get('genre_ids') or [g['id'] for g in m.get('genres', [])])
    def document(m):
        return ' '.join([m.get('title',''), m.get('overview',''),
                         ' '.join('genre'+str(g) for g in genre_ids(m))])
    seeds = seeds or []
    similarities = [0.0] * len(candidates)
    if seeds:
        try:
            matrix = TfidfVectorizer(stop_words='english', ngram_range=(1,2)).fit_transform([document(m) for m in seeds+candidates])
            similarities = cosine_similarity(matrix[len(seeds):], matrix[:len(seeds)]).max(axis=1).tolist()
        except ValueError:
            pass
    wanted = set(preferred_genres)
    seed_genres = set().union(*(genre_ids(s) for s in seeds)) if seeds else set()
    result = []
    for movie, similarity in zip(candidates, similarities):
        genres = genre_ids(movie)
        shared = genres & (wanted | seed_genres)
        overlap = len(shared)/max(len(genres | wanted | seed_genres),1)
        quality = min(float(movie.get('vote_average') or 0)/10, 1)
        score = .75*similarity + .20*overlap + .05*quality
        item = dict(movie)
        item['match_score'] = round(score, 4)
        item['reason'] = ('Plot similarity and shared genres' if seeds and shared else 'Plot similarity' if seeds else 'Your preferred genres' if shared else 'Popular discovery pick')
        result.append(item)
    return sorted(result, key=lambda m: m['match_score'], reverse=True)[:limit]
