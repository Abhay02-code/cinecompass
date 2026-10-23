import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app import create_app
from accounts import safe_next
from database import User
from extensions import db, cache

PASSWORD = 'account-test-password-123'

class AccountTests(unittest.TestCase):
    def setUp(self):
        self.config={'TESTING':True,'SECRET_KEY':'fixed-test-key-1234567890','SQLALCHEMY_DATABASE_URI':'sqlite://', 'WTF_CSRF_ENABLED':False,'RATELIMIT_ENABLED':False,'TMDB_READ_TOKEN':''}
        self.app=create_app(self.config)
        self.ctx=self.app.app_context();self.ctx.push();db.create_all();cache.clear()
        self.client=self.app.test_client()
    def tearDown(self):
        db.session.remove();db.drop_all();cache.clear();self.ctx.pop()
    def register(self, username='abhay', **extra):
        return self.client.post('/register',data={'username':username,'password':PASSWORD,'confirm':PASSWORD,**extra})
    def signin(self, **extra):
        return self.client.post('/login',data={'username':'abhay','password':PASSWORD,**extra})
    def token(self, page):
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',page.data.decode()).group(1)

    def test_username_normalization(self):
        self.assertEqual(self.register('  AbHay_01  ').status_code,302)
        self.assertEqual(db.session.scalar(select(User)).username,'abhay_01')
        self.client.post('/logout')
        result=self.client.post('/login',data={'username':'  ABHAY_01  ','password':PASSWORD})
        self.assertEqual(result.location,'/library')

    def test_signup_field_errors(self):
        result=self.client.post('/register',data={'username':'ab','password':'short','confirm':'different'})
        self.assertEqual(result.status_code,400)
        self.assertIn('Use 3–40 characters'.encode(),result.data)
        self.assertIn('10–128 characters'.encode(),result.data)
        self.assertIn(b'Your passwords do not match',result.data)
        self.assertEqual(db.session.query(User).count(),0)
        self.assertNotIn(b'value="short"',result.data)

    def test_duplicate_case_insensitive(self):
        self.register();self.client.post('/logout')
        result=self.register('ABHAY')
        self.assertEqual(result.status_code,409)
        self.assertIn(b'This username is taken',result.data)
        self.assertEqual(db.session.query(User).count(),1)

    def test_wrong_password_and_unknown_user(self):
        self.register();self.client.post('/logout')
        for username in ('abhay','missing'):
            result=self.client.post('/login',data={'username':username,'password':'wrong-password-123'})
            self.assertEqual(result.status_code,401)
            self.assertIn(b'Invalid username or password',result.data)
            self.assertNotIn(b'value="wrong-password-123"',result.data)
        self.assertEqual(self.client.get('/library').status_code,302)

    def test_login_returns_to_requested_page(self):
        self.register();self.client.post('/logout')
        self.assertEqual(self.signin(next_url='/movie/157336#reviews').location,'/movie/157336#reviews')
        self.assertEqual(self.client.get('/library').status_code,200)

    def test_signup_returns_to_requested_page(self):
        self.assertEqual(self.register(next_url='/for-you').location,'/for-you')

    def test_safe_redirects(self):
        for target in ('https://evil.example','//evil.example','/\\evil.example','/%2f%2fevil.example','/%255cevil.example','javascript:alert(1)','/\nevil.example','/login','/register','/logout'):
            self.assertIsNone(safe_next(target),target)
        self.assertEqual(safe_next('/movie/123?x=1#reviews'),'/movie/123?x=1#reviews')
        self.register();self.client.post('/logout')
        self.assertEqual(self.signin(next_url='https://evil.example').location,'/library')

    def test_remember_and_logout_clear_both_cookies(self):
        self.register();self.client.post('/logout')
        self.assertEqual(self.signin(remember='y').status_code,302)
        self.assertIsNotNone(self.client.get_cookie('remember_token'))
        self.client.delete_cookie('session')
        self.assertEqual(self.client.get('/library').status_code,200)
        self.client.post('/logout')
        self.assertIsNone(self.client.get_cookie('remember_token'))
        self.assertEqual(self.client.get('/library').status_code,302)

    def test_default_login_does_not_remember(self):
        self.register();self.client.post('/logout');self.signin()
        self.assertIsNone(self.client.get_cookie('remember_token'))

    def test_fresh_forms_are_not_cached(self):
        for path in ('/login','/register'):
            response=self.client.get(path)
            self.assertIn('no-store',response.headers['Cache-Control'])
            self.assertEqual(response.headers['Pragma'],'no-cache')

    def test_csrf_failure_recovers_with_fresh_form(self):
        self.register();self.client.post('/logout')
        self.app.config['WTF_CSRF_ENABLED']=True
        old_token=self.token(self.client.get('/login'))
        bad=self.client.post('/login',data={'username':'abhay','password':PASSWORD,'csrf_token':'expired','next_url':'/library'})
        self.assertEqual(bad.status_code,400)
        self.assertIn(b'This form expired',bad.data)
        self.assertNotIn(PASSWORD.encode(),bad.data)
        fresh=self.token(bad)
        self.assertNotEqual(fresh,old_token)
        result=self.client.post('/login',data={'username':'abhay','password':PASSWORD,'csrf_token':fresh,'next_url':'/library'})
        self.assertEqual(result.location,'/library')

    def test_logout_stays_csrf_protected(self):
        self.register();self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/logout').status_code,400)
        self.assertEqual(self.client.get('/library').status_code,200)

    def test_friendly_database_error(self):
        with patch('accounts.db.session.scalar',side_effect=SQLAlchemyError('private database details')):
            result=self.signin()
        self.assertEqual(result.status_code,503)
        self.assertIn(b'Accounts are temporarily unavailable',result.data)
        self.assertNotIn(b'private database details',result.data)
        with patch('accounts.db.session.commit',side_effect=SQLAlchemyError('private database details')):
            result=self.register()
        self.assertEqual(result.status_code,503)
        self.assertNotIn(b'private database details',result.data)

    def test_invalid_session_identity(self):
        with self.client.session_transaction() as session:session['_user_id']='not-an-id'
        self.assertEqual(self.client.get('/library').status_code,302)

    def test_authenticated_user_redirects(self):
        self.register()
        self.assertEqual(self.client.get('/login').location,'/library')
        self.assertEqual(self.client.get('/register?next=/for-you').location,'/for-you')

    def test_restart_with_same_key_and_database(self):
        with tempfile.TemporaryDirectory() as directory:
            config={**self.config,'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(Path(directory)/'accounts.db')}
            first=create_app(config)
            with first.app_context():db.create_all()
            c1=first.test_client()
            c1.post('/register',data={'username':'restart_user','password':PASSWORD,'confirm':PASSWORD})
            cookie=c1.get_cookie('session')
            second=create_app(config)
            c2=second.test_client();c2.set_cookie('session',cookie.value)
            self.assertEqual(c2.get('/library').status_code,200)
            c2.post('/logout')
            self.assertEqual(c2.post('/login',data={'username':'restart_user','password':PASSWORD}).location,'/library')
            for instance in (first,second):
                with instance.app_context():db.session.remove();db.engine.dispose()

if __name__=='__main__':unittest.main()
