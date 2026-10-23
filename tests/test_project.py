import os
import unittest
from unittest.mock import patch, Mock
from sqlalchemy import select
from app import create_app
from extensions import db, cache
from database import User, WatchItem, Analysis
from werkzeug.security import generate_password_hash
import ml
import tmdb

FILM={'id':1,'title':'Space Journey','overview':'An astronaut explores Mars and survives in space.','genre_ids':[878], 'genres':[{'id':878,'name':'Science fiction'}], 'release_date':'2020-01-01','runtime':120,'vote_average':8,'vote_count':10,'original_language':'en','credits':{'cast':[]},'videos':{'results':[]}}
OTHER={'id':2,'title':'Mars Rescue','overview':'An astronaut survives a journey through space on Mars.', 'genre_ids':[878], 'vote_average':7, 'release_date':'2021-01-01'}
COMEDY={'id':3,'title':'Family Lunch','overview':'A funny family reunion over lunch.', 'genre_ids':[35],'vote_average':7}

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app({'TESTING':True,'SECRET_KEY':'test-secret','SQLALCHEMY_DATABASE_URI':'sqlite://', 'WTF_CSRF_ENABLED':False,'RATELIMIT_ENABLED':False,'TMDB_READ_TOKEN':''})
        self.ctx=self.app.app_context(); self.ctx.push(); db.create_all(); cache.clear()
        self.client=self.app.test_client()
    def tearDown(self):
        db.session.remove(); db.drop_all(); cache.clear(); self.ctx.pop()
    def register(self,name='abhay'):
        return self.client.post('/register',data={'username':name,'password':'a-strong-password','confirm':'a-strong-password'})
    def test_configuration_and_model_page(self):
        self.assertIn(b'Taking a short intermission',self.client.get('/').data)
        self.assertNotIn(b'Connect your movie catalogue',self.client.get('/').data)
        self.assertNotIn(b'TMDB_READ_TOKEN',self.client.get('/').data)
        self.assertNotIn(b'DEMO MODE',self.client.get('/').data)
        self.assertEqual(self.client.get('/model').status_code,200)
        self.assertEqual(self.client.get('/health').json['status'],'ok')
    def test_register_login_logout(self):
        self.assertEqual(self.register().status_code,302)
        user=db.session.scalar(select(User))
        self.assertNotEqual(user.password_hash,'a-strong-password')
        self.client.post('/logout')
        self.assertIn(b'Invalid username or password',self.client.post('/login',data={'username':'abhay','password':'wrong'}).data)
        self.assertEqual(self.client.post('/login',data={'username':'abhay','password':'a-strong-password'}).status_code,302)
    def test_duplicate_registration(self):
        self.register(); self.client.post('/logout')
        self.assertIn(b'already taken',self.register().data)
    def test_validation(self):
        for data in ({},[],{'text':5},{'text':' '},{'text':'x'*5001},{'text':'good movie','save':'yes'}):
            self.assertEqual(self.client.post('/api/analyze',json=data).status_code,400)
        self.assertEqual(self.client.get('/?genre=999').status_code,400)
        self.assertEqual(self.client.get('/?year=abc').status_code,400)
        self.assertEqual(self.client.get('/?page=abc').status_code,400)
    def test_real_model_and_history(self):
        result=self.client.post('/api/analyze',json={'text':'A wonderful and delightful movie with excellent performances.'})
        self.assertEqual(result.status_code,200)
        self.assertGreater(result.json['positive_probability'],.5)
        result=ml.analyze('A terrible boring movie with awful acting and a stupid story.')
        self.assertLess(result['positive_probability'],.5)
        self.assertEqual(self.client.post('/api/analyze',json={'text':'great film','save':True}).status_code,401)
        self.register()
        self.client.post('/api/analyze',json={'text':'great film','save':True})
        row=db.session.scalar(select(Analysis)); self.assertIsNotNone(row)
        self.assertIn(b'great film',self.client.get('/library').data)
        self.client.post(f'/history/{row.id}/delete')
        self.assertEqual(db.session.query(Analysis).count(),0)
    def test_csrf_enforced(self):
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/api/analyze',json={'text':'great film'}).status_code,400)
        self.assertEqual(self.client.post('/register',data={'username':'test'}).status_code,400)
        import re
        page=self.client.get('/').data.decode()
        token=re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
        self.assertEqual(self.client.post('/api/analyze',json={'text':'great film'},headers={'X-CSRFToken':token}).status_code,200)
    @patch('tmdb.detail',return_value=FILM)
    def test_watchlist_and_preferences(self,fake):
        self.assertEqual(self.client.post('/watchlist/1',data={'action':'save'}).status_code,302)
        self.register()
        self.client.post('/watchlist/1',data={'action':'save'})
        self.client.post('/watchlist/1',data={'action':'save'})
        self.assertEqual(db.session.query(WatchItem).count(),1)
        self.client.post('/watchlist/1',data={'action':'like'})
        self.assertTrue(db.session.scalar(select(WatchItem)).liked)
        self.client.post('/library',data={'genres':['878','18']})
        self.assertEqual(db.session.scalar(select(User)).genres,'878,18')
        self.client.post('/watchlist/1',data={'action':'remove'})
        self.assertEqual(db.session.query(WatchItem).count(),0)
    def test_history_isolation(self):
        self.register()
        self.client.post('/api/analyze',json={'text':'good film','save':True})
        identity=db.session.scalar(select(Analysis)).id
        self.client.post('/logout'); self.register('another')
        self.assertEqual(self.client.post(f'/history/{identity}/delete').status_code,404)
        self.assertEqual(db.session.query(Analysis).count(),1)
    def test_recommendation_ranking(self):
        ranked=ml.recommend([FILM],[FILM,COMEDY,OTHER,OTHER],exclude=[1])
        self.assertEqual([x['id'] for x in ranked],[2,3])
        self.assertGreater(ranked[0]['match_score'],ranked[1]['match_score'])
    @patch('tmdb.fetch')
    def test_live_search(self,fake):
        self.app.config['TMDB_READ_TOKEN']='test-token'
        fake.return_value={'results':[FILM],'total_pages':2}
        page=self.client.get('/?q=space&year=2020')
        self.assertIn(b'Space Journey',page.data)
        self.assertIn(b'Next',page.data)
        self.assertNotIn(b'Connect your movie catalogue',page.data)
    @patch('tmdb.candidates',return_value=([OTHER,COMEDY],[]))
    @patch('tmdb.reviews',return_value=([],0,0))
    @patch('tmdb.detail',return_value=FILM)
    def test_detail_empty_reviews(self,*mocks):
        page=self.client.get('/movie/1')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'No review sentiment estimate',page.data)
        self.assertIn(b'Mars Rescue',page.data)
    @patch('tmdb.candidates',return_value=([OTHER,COMEDY],[]))
    @patch('tmdb.discover',return_value={'results':[OTHER,COMEDY]})
    @patch('tmdb.detail',return_value=FILM)
    def test_personalisation(self,*mocks):
        self.register(); self.client.post('/watchlist/1',data={'action':'like'})
        self.assertEqual(self.client.get('/for-you').status_code,200)
        self.assertIn(b'Mars Rescue',self.client.get('/for-you').data)
    @patch('tmdb.requests.get')
    def test_api_failures(self,fake):
        import requests
        self.app.config['TMDB_READ_TOKEN']='token'
        fake.side_effect=requests.Timeout()
        self.assertIn(b'Movies could not be loaded',self.client.get('/?q=test').data)
        fake.side_effect=None; fake.return_value=Mock(status_code=401)
        cache.clear()
        self.assertIn(b'Movie search is temporarily unavailable',self.client.get('/?q=test').data)
    @patch('tmdb.fetch')
    def test_review_dedup_and_cap(self,fake):
        fake.return_value={'total_results':60,'total_pages':3,'results':[{'id':'one','author':'A','content':'great film'}]}
        reviews,total,truncated=tmdb.reviews(99)
        self.assertEqual(len(reviews),1)
        self.assertEqual(fake.call_count,3)
    def test_xss_and_headers(self):
        page=self.client.get('/?q=<script>alert(1)</script>')
        self.assertNotIn(b'<script>alert(1)',page.data)
        self.assertEqual(page.headers['X-Frame-Options'],'DENY')
        self.assertIn("default-src 'self'",page.headers['Content-Security-Policy'])

    @patch('tmdb.search')
    def test_autocomplete_results(self, fake):
        self.app.config['TMDB_READ_TOKEN'] = 'token'
        fake.return_value = {'results': [FILM, FILM, dict(OTHER, adult=True), dict(COMEDY, poster_path=None)]}
        response = self.client.get('/api/search?q=space')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m['id'] for m in response.json['results']], [1, 3])
        self.assertEqual(response.json['results'][0]['url'], '/movie/1')
        self.assertEqual(response.json['results'][0]['year'], '2020')
        self.assertEqual(response.json['results'][0]['genres'], ['Science fiction'])
        self.assertNotIn('overview', response.json['results'][0])

    @patch('tmdb.search')
    def test_autocomplete_short_invalid_and_failure(self, fake):
        self.assertEqual(self.client.get('/api/search?q=s').json, {'results': []})
        fake.assert_not_called()
        self.assertEqual(self.client.get('/api/search?q='+'x'*101).status_code, 400)
        self.assertEqual(self.client.get('/api/search?q=film&year=abc').status_code, 400)
        fake.side_effect = tmdb.MovieError('Search temporarily unavailable.', 503)
        response = self.client.get('/api/search?q=space')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['error'], 'Search temporarily unavailable.')

    def test_autocomplete_requires_live_credentials(self):
        response = self.client.get('/api/search?q=interstellar')
        self.assertEqual(response.status_code, 503)
        self.assertIn('temporarily unavailable', response.json['error'])
        self.assertNotIn('TOKEN', response.json['error'])

    @patch('tmdb.candidates', return_value=([], []))
    @patch('tmdb.reviews', return_value=([{'author': 'Viewer', 'content': 'Wonderful film with excellent acting.', 'id': 'r1'}], 1, 0))
    @patch('tmdb.detail', return_value=FILM)
    def test_movie_reviews_are_visible(self, *mocks):
        page = self.client.get('/movie/1')
        self.assertIn(b'class="audience-review"', page.data)
        self.assertIn(b'Wonderful film with excellent acting.', page.data)
        self.assertIn(b'id="reviews"', page.data)
        self.assertIn(b'role="combobox"', page.data)

    def test_deployment_version_and_asset_refresh(self):
        status = self.client.get('/api/status')
        self.assertEqual(status.json['version'], '3.0.1')
        self.assertFalse(status.json['movie_data_configured'])
        self.assertEqual(set(status.json), {'version', 'movie_data_configured'})
        self.assertEqual(status.headers['Cache-Control'], 'no-store')
        self.assertIn(b'app.js?v=3.0.1', self.client.get('/').data)
        self.assertIn(b'style.css?v=3.0.1', self.client.get('/').data)

if __name__=='__main__': unittest.main()
