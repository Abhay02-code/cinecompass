import os
import requests
from flask import current_app
from extensions import cache

GENRES = {28:'Action',12:'Adventure',16:'Animation',35:'Comedy',80:'Crime',99:'Documentary',18:'Drama',10751:'Family',14:'Fantasy',36:'History',27:'Horror',10402:'Music',9648:'Mystery',10749:'Romance',878:'Science fiction',10770:'TV movie',53:'Thriller',10752:'War',37:'Western'}

class MovieError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def configured():
    return bool(current_app.config.get('TMDB_READ_TOKEN'))


@cache.memoize(timeout=600)
def fetch(path, **params):
    token = current_app.config.get('TMDB_READ_TOKEN')
    if not token:
        raise MovieError('Add your TMDB API Read Access Token to .env (or Render Environment) to enable live movies.', 503)
    try:
        response = requests.get('https://api.themoviedb.org/3/'+path,
                                headers={'Authorization': 'Bearer '+token},
                                params={'language':'en-US', **params}, timeout=(3, 8))
        if response.status_code in (401,403):
            raise MovieError('TMDB rejected the token. Check your API Read Access Token.', 503)
        if response.status_code == 404:
            raise MovieError('Movie not found.', 404)
        if response.status_code == 429:
            raise MovieError('TMDB is busy. Please wait a moment and try again.', 503)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        # Never log exception URLs/headers, which could include sensitive configuration.
        raise MovieError('Cannot reach TMDB. Check network connectivity and try again.', 502) from exc


def search(query, page=1, year=None):
    params = {'query':query, 'page':page, 'include_adult':'false'}
    if year: params['primary_release_year'] = year
    return fetch('search/movie', **params)


def discover(page=1, genre=None, language=None, sort='popularity.desc'):
    params = {'page':page, 'sort_by':sort, 'include_adult':'false', 'vote_count.gte':50}
    if genre: params['with_genres'] = genre
    if language: params['with_original_language'] = language
    return fetch('discover/movie', **params)


def detail(movie_id):
    movie = fetch(f'movie/{movie_id}', append_to_response='credits,videos')
    if movie.get('adult'):
        raise MovieError('This title is outside this app’s catalogue.', 404)
    return movie


@cache.memoize(timeout=600)
def reviews(movie_id):
    # A bounded sample, not all audience opinion. Deduplicate across pages.
    collected, seen, total, truncated = [], set(), 0, 0
    for page in range(1,4):
        data = fetch(f'movie/{movie_id}/reviews', page=page)
        total = data.get('total_results', 0)
        for item in data.get('results', []):
            text = item.get('content','').strip()
            identity = item.get('id') or text
            if text and identity not in seen:
                seen.add(identity)
                truncated += int(len(text)>12000)
                collected.append({'author':item.get('author','Anonymous'), 'content':text[:12000], 'id':identity})
        if page >= data.get('total_pages',1): break
    return collected[:60], total, truncated


@cache.memoize(timeout=900)
def candidates(movie_id):
    pool, warnings = [], []
    for path in (f'movie/{movie_id}/similar', 'discover/movie'):
        try:
            pool.extend(fetch(path, page=1, include_adult='false').get('results',[]))
        except MovieError:
            warnings.append('Some recommendation candidates could not be loaded.')
    return pool, warnings
