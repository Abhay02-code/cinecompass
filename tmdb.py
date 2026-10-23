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
        current_app.logger.error('MOVIE_DATA_NOT_CONFIGURED: TMDB_READ_TOKEN is missing from the web service Environment.')
        raise MovieError('Movie search is temporarily unavailable. Please try again later.', 503)
    try:
        response = requests.get('https://api.themoviedb.org/3/'+path,
                                headers={'Authorization': 'Bearer '+token},
                                params={'language':'en-US', **params}, timeout=(3, 8))
        if response.status_code in (401,403):
            current_app.logger.error('MOVIE_DATA_AUTH_FAILED: TMDB rejected the server credential (HTTP %s). Replace TMDB_READ_TOKEN in the web service Environment.', response.status_code)
            raise MovieError('Movie search is temporarily unavailable. Please try again later.', 503)
        if response.status_code == 404:
            raise MovieError('Movie not found.', 404)
        if response.status_code == 429:
            raise MovieError('TMDB is busy. Please wait a moment and try again.', 503)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        # Never log exception URLs/headers, which could include sensitive configuration.
        current_app.logger.error('MOVIE_DATA_UPSTREAM_FAILED: %s while contacting the movie provider.', type(exc).__name__)
        raise MovieError('Movies could not be loaded right now. Please try again shortly.', 502) from exc


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


def discover_free(region='IN', mode='all', page=1):
    """Only free/advertising offers; never include subscription/rental/purchase."""
    return fetch('discover/movie',page=page,watch_region=region,
                 with_watch_monetization_types='free|ads' if mode=='all' else mode,
                 include_adult='false',sort_by='popularity.desc')


def watch_providers(movie_id):
    return fetch(f'movie/{movie_id}/watch/providers')
