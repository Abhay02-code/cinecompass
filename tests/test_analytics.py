import csv
import io
import re
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app import create_app
from analytics import CONSENT_COOKIE, VISITOR_COOKIE, utc_today
from database import User, DailyMetric, DailyVisitor
from extensions import db, cache


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app({'TESTING':True,'SECRET_KEY':'analytics-test-secret',
                             'SQLALCHEMY_DATABASE_URI':'sqlite://','WTF_CSRF_ENABLED':False,
                             'RATELIMIT_ENABLED':False,'TMDB_READ_TOKEN':'','ADMIN_USER_ID':None})
        self.ctx=self.app.app_context();self.ctx.push();db.create_all();cache.clear()
        self.client=self.app.test_client()

    def tearDown(self):
        db.session.remove();db.drop_all();self.ctx.pop()

    def count(self,kind):
        return db.session.scalar(select(func.sum(DailyMetric.count)).where(DailyMetric.kind==kind)) or 0

    def allow(self,client=None):
        return (client or self.client).post('/privacy/analytics',data={'choice':'yes'})

    def user(self,name='owner',owner=True):
        user=User(username=name,password_hash=generate_password_hash('correct-password'))
        db.session.add(user);db.session.commit()
        if owner:self.app.config['ADMIN_USER_ID']=user.id
        return user.id

    def signin(self,name='owner'):
        return self.client.post('/login',data={'username':name,'password':'correct-password'})

    def test_creator_credit_and_about(self):
        page=self.client.get('/')
        self.assertIn(b'Built by',page.data)
        self.assertIn(b'Abhay Kumar Aditya',page.data)
        self.assertIn(b'https://github.com/Abhay02-code',page.data)
        self.assertIn(b'TMDB',page.data)
        self.assertIn(b'BIT Mesra',self.client.get('/about').data)
        self.assertIn(b'Anonymous usage measurement',self.client.get('/privacy').data)

    def test_no_consent_and_decline_do_not_collect(self):
        self.client.get('/about')
        self.assertEqual(db.session.query(DailyVisitor).count(),0)
        self.assertEqual(self.count('page_view'),0)
        response=self.client.post('/privacy/analytics',data={'choice':'no'})
        self.assertEqual(response.status_code,302)
        self.assertIsNone(self.client.get_cookie(VISITOR_COOKIE))
        self.client.get('/about')
        self.assertEqual(self.count('page_view'),0)

    def test_opt_in_counts_views_and_deduplicates_browser(self):
        self.allow();self.client.get('/about');self.client.get('/model')
        self.assertEqual(self.count('page_view'),2)
        self.assertEqual(db.session.query(DailyVisitor).count(),1)
        cookie=self.client.get_cookie(VISITOR_COOKIE)
        self.assertTrue(cookie.http_only);self.assertEqual(cookie.same_site,'Lax')
        other=self.app.test_client();self.allow(other);other.get('/about')
        self.assertEqual(db.session.query(DailyVisitor).count(),2)

    def test_dnt_gpc_bots_and_owner_excluded(self):
        self.allow()
        for headers in ({'DNT':'1'},{'Sec-GPC':'1'},{'User-Agent':'Googlebot'}):
            self.client.get('/about',headers=headers)
        self.assertEqual(self.count('page_view'),0)
        self.user();self.signin();self.client.get('/about')
        self.assertEqual(self.count('page_view'),0)
        self.assertIn(b'Analytics</a>',self.client.get('/library').data)

    def test_privacy_signal_overrides_allow(self):
        self.client.post('/privacy/analytics',data={'choice':'yes'},headers={'Sec-GPC':'1'})
        self.assertEqual(self.client.get_cookie(CONSENT_COOKIE).value,'no')

    def test_opt_out_deletes_cookie_and_stops_measurement(self):
        self.allow();self.client.get('/about')
        self.assertIsNotNone(self.client.get_cookie(VISITOR_COOKIE))
        self.client.post('/privacy/analytics',data={'choice':'no'})
        self.assertIsNone(self.client.get_cookie(VISITOR_COOKIE))
        self.client.get('/about');self.assertEqual(self.count('page_view'),1)

    def test_no_admin_by_default_and_access_is_owner_only(self):
        self.assertEqual(self.client.get('/admin/analytics').status_code,302)
        self.user(owner=False);self.signin()
        self.assertEqual(self.client.get('/admin/analytics').status_code,403)
        self.assertEqual(self.client.get('/admin/analytics.csv').status_code,403)
        self.app.config['ADMIN_USER_ID']=999
        self.assertEqual(self.client.get('/admin/analytics').status_code,403)
        self.app.config['ADMIN_USER_ID']=db.session.scalar(select(User.id))
        self.assertEqual(self.client.get('/admin/analytics').status_code,200)

    def test_successful_actions_only_and_no_sensitive_text_saved(self):
        self.allow()
        with patch('tmdb.search',return_value={'results':[]}):
            self.client.get('/api/search?q=private-search-title')
            self.client.get('/api/search?q=x')
        self.client.post('/api/analyze',json={'text':'private review: This movie is good'})
        self.client.post('/api/analyze',json={'text':''})
        self.client.get('/about?secret=private-query')
        self.assertEqual(self.count('search_request'),1)
        self.assertEqual(self.count('analysis'),1)
        self.assertEqual(self.count('page_view'),1)
        for row in db.session.scalars(select(DailyMetric)):
            self.assertNotIn('private',row.path)
            self.assertNotIn('?',row.path)
        self.assertEqual(set(DailyVisitor.__table__.columns.keys()),{'day','visitor_hash'})
        self.assertEqual(set(DailyMetric.__table__.columns.keys()),{'day','kind','path','count'})

    def test_failed_search_and_non_content_routes_excluded(self):
        self.allow();self.client.get('/api/search?q=interstellar')
        for path in ('/health','/api/status','/login','/register','/privacy','/missing','/static/app.js'):
            self.client.get(path)
        self.assertEqual(db.session.query(DailyMetric).count(),0)

    def test_range_report_distinct_visitors_csv_and_account_counts(self):
        today=utc_today();yesterday=today-timedelta(days=1)
        self.user()
        db.session.add_all([DailyVisitor(day=today,visitor_hash='a'*64),
                            DailyVisitor(day=yesterday,visitor_hash='a'*64),
                            DailyVisitor(day=today,visitor_hash='b'*64),
                            DailyMetric(day=today,kind='page_view',path='/about',count=3),
                            DailyMetric(day=yesterday,kind='analysis',path='/api/analyze',count=2)])
        db.session.commit();self.signin()
        page=self.client.get('/admin/analytics?days=7')
        self.assertIn(b'data-stat="visitors">2<',page.data)
        self.assertIn(b'data-stat="accounts">1<',page.data)
        self.assertIn(b'data-stat="analyses">2<',page.data)
        self.assertIn('no-store',page.headers['Cache-Control'])
        export=self.client.get('/admin/analytics.csv?days=7')
        rows=list(csv.reader(io.StringIO(export.data.decode())))
        self.assertEqual(len(rows),8)
        self.assertEqual(sum(int(r[2]) for r in rows[1:]),3)
        self.assertIn('attachment',export.headers['Content-Disposition'])
        for value in ('0','365','abc'):
            self.assertEqual(self.client.get('/admin/analytics?days='+value).status_code,400)

    def test_retention_and_explicit_cleanup(self):
        old=utc_today()-timedelta(days=90);edge=utc_today()-timedelta(days=89)
        for day in (old,edge):
            db.session.add(DailyVisitor(day=day,visitor_hash='a'*64))
            db.session.add(DailyMetric(day=day,kind='page_view',path='/about',count=1))
        db.session.commit()
        result=self.app.test_cli_runner().invoke(args=['prune-analytics'])
        self.assertEqual(result.exit_code,0)
        self.assertEqual(db.session.query(DailyVisitor).count(),1)
        self.assertEqual(db.session.query(DailyMetric).count(),1)
        self.allow();self.client.get('/about');self.assertEqual(self.count('page_view'),2)

    def test_invalid_visitor_cookie_rotates_and_storage_failure_serves_page(self):
        self.allow();self.client.set_cookie(VISITOR_COOKIE,'tampered')
        self.client.get('/about')
        self.assertNotEqual(self.client.get_cookie(VISITOR_COOKIE).value,'tampered')
        with patch('analytics.increment',side_effect=SQLAlchemyError('not exposed')):
            response=self.client.get('/about')
        self.assertEqual(response.status_code,200)
        self.assertNotIn(b'not exposed',response.data)
        self.assertEqual(self.count('page_view'),1)

    def test_consent_csrf_and_local_redirect(self):
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/privacy/analytics',data={'choice':'yes'}).status_code,400)
        page=self.client.get('/privacy').data.decode()
        token=re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
        response=self.client.post('/privacy/analytics',data={'choice':'yes','csrf_token':token,'next':'https://evil.example'})
        self.assertEqual(response.location,'/privacy')
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.client.post('/privacy/analytics',data={'choice':'bad','csrf_token':token}).status_code,400)

    def test_new_tables_do_not_destroy_existing_accounts(self):
        identity=self.user()
        # init_db.py uses create_all, which adds missing tables without rewriting User.
        DailyMetric.__table__.drop(db.engine);DailyVisitor.__table__.drop(db.engine)
        db.create_all()
        self.assertEqual(db.session.get(User,identity).username,'owner')
        self.assertEqual(db.session.query(DailyMetric).count(),0)

if __name__=='__main__':unittest.main()
