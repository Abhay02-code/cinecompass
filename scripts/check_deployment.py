"""Check a deployed release without reading or transmitting any credentials."""
import argparse
import sys
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url', help='Public service URL, e.g. https://cinecompass-2.onrender.com')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    if not base.startswith(('http://', 'https://')):
        parser.error('Use a complete http:// or https:// service URL.')
    try:
        status = requests.get(base + '/api/status', timeout=60)
        if status.status_code == 404:
            print('OLD RELEASE: /api/status is missing. Push the patch and deploy the latest commit.')
            return 1
        status.raise_for_status()
        data = status.json()
        print('Deployed version:', data.get('version', 'unknown'))
        print('Movie credential configured:', bool(data.get('movie_data_configured')))
        print('Shared account database:', bool(data.get('shared_account_database')))
        if data.get('version') != '3.4.0':
            print('OLD RELEASE: deploy the latest 3.4.0 patch commit.')
            return 1
        if not data.get('shared_account_database'):
            print('ACTION: configure persistent PostgreSQL DATABASE_URL and APP_ENV=production.')
            return 1
        health = requests.get(base + '/health', timeout=30)
        if health.status_code != 200:
            print('DATABASE HEALTH FAILED: check DATABASE_URL and table initialization in Render logs.')
            return 1
        if not data.get('movie_data_configured'):
            print('ACTION: Set TMDB_READ_TOKEN on this WEB SERVICE in Render Environment. Save, rebuild and deploy.')
            return 1
        result = requests.get(base + '/api/search', params={'q': 'interstellar'}, timeout=30)
        payload = result.json()
        if result.status_code != 200:
            print('SEARCH FAILED:', result.status_code)
            print('Check Render logs for MOVIE_DATA_AUTH_FAILED or MOVIE_DATA_UPSTREAM_FAILED.')
            return 1
        print('Search endpoint: OK')
        print('Returned movie matches:', len(payload.get('results', [])))
        print('Open the homepage and hard-refresh (Ctrl+Shift+R).')
        return 0
    except (requests.RequestException, ValueError):
        print('CHECK FAILED: The service did not return a readable response. Check its URL and Render deployment logs.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
