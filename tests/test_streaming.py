import re
import unittest
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select
from app import create_app
from analytics import utc_today
from database import User, FreeWatchLink, MovieReview
from extensions import db, cache
from streaming import availability, safe_provider_url, tmdb_watch_url
from tests.test_project import FILM, OTHER
import tmdb

PROVIDERS={'results':{'IN':{'link':'https://www.themoviedb.org/movie/1/watch?locale=IN',
    'free':[{'provider_id':1,'provider_name':'Free Cinema','logo_path':'/logo.png'}],
    'ads':[{'provider_id':2,'provider_name':'Ad Cinema','logo_path':None}],
    'flatrate':[{'provider_id':3,'provider_name':'Subscription Only'}],
    'rent':[{'provider_id':4,'provider_name':'Rental Only'}],
    'buy':[{'provider_id':5,'provider_name':'Purchase Only'}]},
    'US':{'free':[{'provider_id':6,'provider_name':'US Cinema'}]}}}

class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app({'TESTING':True,'SECRET_KEY':'streaming-test-secret',
            'SQLALCHEMY_DATABASE_URI':'sqlite://','WTF_CSRF_ENABLED':False,
            'RATELIMIT_ENABLED':False,'TMDB_READ_TOKEN':'','ADMIN_USER_ID':None})
        self.ctx=self.app.app_context();self.ctx.push();db.create_all();cache.clear()
        self.client=self.app.test_client()
        self.patches=[patch('tmdb.detail',return_value=FILM),patch('tmdb.reviews',return_value=([],0,0)),
                      patch('tmdb.candidates',return_value=([OTHER],[])),patch('tmdb.watch_providers',return_value=PROVIDERS)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in self.patches:p.stop()
        db.session.remove();db.drop_all();cache.clear();self.ctx.pop()
    def register(self,owner=True):
        self.client.post('/register',data={'username':'abhay','password':'correct-password','confirm':'correct-password'})
        if owner:self.app.config['ADMIN_USER_ID']=db.session.scalar(select(User.id))
    def publish(self,**changes):
        data={'movie_id':1,'region':'IN','provider':'Official channel','kind':'ads',
              'url':'https://www.youtube.com/watch?v=abcdefghijk','confirmed':'y'}
        data.update(changes)
        return self.client.post('/admin/watch-links',data=data)

    @patch('tmdb.fetch',return_value={'results':[]})
    def test_discover_uses_only_free_ads_and_region(self,fake):
        tmdb.discover_free('IN','all',2)
        fake.assert_called_once_with('discover/movie',page=2,watch_region='IN',with_watch_monetization_types='free|ads',include_adult='false',sort_by='popularity.desc')
        fake.reset_mock();tmdb.discover_free('US','free',1)
        self.assertEqual(fake.call_args.kwargs['with_watch_monetization_types'],'free')

    @patch('tmdb.discover_free')
    def test_catalogue_filters_pagination_country_and_no_fake_links(self,fake):
        fake.return_value={'results':[FILM,dict(OTHER,adult=True)],'total_pages':3}
        page=self.client.get('/free-movies?watch_region=US&mode=ads&page=2')
        self.assertEqual(page.status_code,200);fake.assert_called_once_with('US','ads',2)
        self.assertIn(b'Space Journey',page.data);self.assertNotIn(b'Mars Rescue',page.data)
        self.assertIn(b'watch_region=US',page.data);self.assertIn(b'JustWatch',page.data)
        self.assertNotIn(b'Watch free on',page.data)
        self.assertIn(b'Next',page.data);self.assertIn(b'Previous',page.data)

    @patch('tmdb.discover_free',return_value={'results':[],'total_pages':0})
    def test_empty_catalogue_and_validated_filters(self,fake):
        self.assertIn(b'No free listings reported',self.client.get('/free-movies').data)
        for query in ('watch_region=XX','mode=flatrate','mode=rent','page=0','page=501','page=abc'):
            self.assertEqual(self.client.get('/free-movies?'+query).status_code,400)
        self.assertEqual(self.client.get('/movie/1?watch_region=XX').status_code,400)

    def test_provider_availability_filters_paid_and_other_countries(self):
        result=availability(1,'IN')
        self.assertEqual([o['name'] for o in result['offers']],['Free Cinema','Ad Cinema'])
        self.assertEqual([o['kind'] for o in result['offers']],['free','ads'])
        page=self.client.get('/movie/1').data
        self.assertIn(b'Free Cinema',page);self.assertNotIn(b'Subscription Only',page)
        self.assertNotIn(b'Rental Only',page);self.assertNotIn(b'US Cinema',page)
        self.assertIn(b'Check free options on TMDB',page)
        self.assertNotIn(b'>Watch free ',page)

    def test_tmdb_link_is_specific_and_safe(self):
        self.assertIsNone(tmdb_watch_url('https://evil.example/movie/1/watch',1))
        self.assertIsNone(tmdb_watch_url('https://www.themoviedb.org/movie/2/watch',1))
        self.assertIsNone(tmdb_watch_url('https://www.themoviedb.org/',1))
        self.assertIsNotNone(tmdb_watch_url('https://www.themoviedb.org/movie/1/watch?locale=IN',1))

    def test_no_reported_offer_is_distinct_from_upstream_failure(self):
        with patch('tmdb.watch_providers',return_value={'results':{}}):
            self.assertIn(b'No free offer reported',self.client.get('/movie/1').data)
        with patch('tmdb.watch_providers',side_effect=tmdb.MovieError('upstream')):
            page=self.client.get('/movie/1')
            self.assertEqual(page.status_code,200)
            self.assertIn(b'availability could not be checked',page.data)
            self.assertNotIn(b'No free offer reported',page.data)

    def test_direct_url_validation(self):
        for url in ('javascript:alert(1)','http://www.youtube.com/watch?v=x','https://user:pass@youtube.com/watch?v=x',
                    'https://youtube.com/','https://youtube.com/search','https://127.0.0.1/movie/1',
                    'https://localhost/movie/1','https://x.internal/movie/1','https://example.com:8080/movie/1',
                    'https://example.com/movie/1%0aevil','https://example.com/\\evil','https://2130706433/movie/1'):
            with self.subTest(url=url):self.assertFalse(safe_provider_url(url))
        for url in ('https://www.youtube.com/watch?v=abcdefghijk','https://watch.plex.tv/movie/a-film'):
            self.assertTrue(safe_provider_url(url))

    def test_owner_only_management_and_csrf(self):
        self.assertEqual(self.client.get('/admin/watch-links').status_code,302)
        self.register(owner=False)
        self.assertEqual(self.client.get('/admin/watch-links').status_code,403)
        self.assertEqual(self.publish().status_code,403)
        self.app.config['ADMIN_USER_ID']=db.session.scalar(select(User.id))
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.publish().status_code,400)
        self.assertEqual(db.session.query(FreeWatchLink).count(),0)

    def test_publish_direct_link_and_deduplicate(self):
        self.register();self.assertEqual(self.publish().status_code,303);self.assertEqual(self.publish().status_code,303)
        self.assertEqual(db.session.query(FreeWatchLink).count(),1)
        row=db.session.scalar(select(FreeWatchLink))
        self.assertEqual(row.movie_title,FILM['title']);self.assertEqual(row.checked_by,db.session.scalar(select(User.id)))
        page=self.client.get('/movie/1').data
        self.assertIn(b'>Watch free ',page)
        self.assertIn(b'https://www.youtube.com/watch?v=abcdefghijk',page)
        self.assertIn(b'Owner checked',page)

    @patch('tmdb.discover_free',return_value={'results':[]})
    def test_expired_country_and_mode_links_excluded(self,fake):
        self.register();self.publish()
        self.assertIn(b'Watch free on',self.client.get('/free-movies?mode=ads').data)
        self.assertNotIn(b'Watch free on',self.client.get('/free-movies?mode=free').data)
        self.assertNotIn(b'Watch free on',self.client.get('/free-movies?watch_region=US').data)
        row=db.session.scalar(select(FreeWatchLink));row.expires_on=utc_today()-timedelta(days=1);db.session.commit()
        self.assertNotIn(b'>Watch free ',self.client.get('/movie/1').data)
        self.assertNotIn(b'Watch free on',self.client.get('/free-movies').data)
        self.assertIn(b'Expired',self.client.get('/admin/watch-links').data)

    def test_renew_confirmation_delete_and_authorization(self):
        self.register();self.publish();row=db.session.scalar(select(FreeWatchLink));identity=row.id
        self.assertEqual(self.client.post(f'/admin/watch-links/{identity}/renew').status_code,400)
        self.assertEqual(self.client.post(f'/admin/watch-links/{identity}/renew',data={'confirmed':'yes'}).status_code,303)
        self.assertEqual(self.client.post(f'/admin/watch-links/{identity}/delete').status_code,303)
        self.assertEqual(db.session.query(FreeWatchLink).count(),0)
        self.assertEqual(self.client.post(f'/admin/watch-links/{identity}/delete').status_code,404)

    def test_admin_form_prefill_validation_and_no_assertion_no_publish(self):
        self.register()
        page=self.client.get('/admin/watch-links?movie_id=1&watch_region=US')
        self.assertIn(b'value="1"',page.data)
        self.assertEqual(self.publish(confirmed='').status_code,400)
        self.assertEqual(self.publish(kind='rent').status_code,400)
        self.assertEqual(self.publish(region='XX').status_code,400)
        self.assertEqual(self.publish(url='https://youtube.com/').status_code,400)
        self.assertEqual(db.session.query(FreeWatchLink).count(),0)

    @patch('tmdb.discover_free',side_effect=tmdb.MovieError('Could not load listings.',502))
    def test_catalogue_failure_keeps_curated_links(self,fake):
        self.register();self.publish()
        page=self.client.get('/free-movies')
        self.assertIn(b'Could not load listings.',page.data)
        self.assertIn(b'Watch free on',page.data)

    def test_additive_table_setup_preserves_accounts(self):
        self.register();identity=db.session.scalar(select(User.id))
        FreeWatchLink.__table__.drop(db.engine);db.create_all()
        self.assertEqual(db.session.get(User,identity).username,'abhay')
        self.assertEqual(db.session.query(FreeWatchLink).count(),0)

if __name__=='__main__':unittest.main()
