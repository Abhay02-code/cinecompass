import unittest
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import create_app
from database import User, MovieReview, now
from extensions import db, cache
from tests.test_project import FILM, OTHER


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app({'TESTING':True,'SECRET_KEY':'community-test-secret',
            'SQLALCHEMY_DATABASE_URI':'sqlite://','WTF_CSRF_ENABLED':False,
            'RATELIMIT_ENABLED':False,'TMDB_READ_TOKEN':'','ADMIN_USER_ID':None})
        self.ctx=self.app.app_context();self.ctx.push();db.create_all();cache.clear()
        self.client=self.app.test_client()
        self.patches=[patch('tmdb.detail',return_value=FILM),
                      patch('tmdb.reviews',return_value=([{'author':'TMDB viewer','content':'Wonderful movie!'}],1,0)),
                      patch('tmdb.candidates',return_value=([OTHER],[]))]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in self.patches:p.stop()
        db.session.remove();db.drop_all();cache.clear();self.ctx.pop()

    def register(self,name='abhay'):
        return self.client.post('/register',data={'username':name,'password':'correct-password','confirm':'correct-password'})

    def save(self,rating=5,body='Wonderful story and performances.'):
        return self.client.post('/movie/1/review',data={'rating':rating,'body':body})

    def test_anonymous_reads_original_and_local_but_cannot_write(self):
        page=self.client.get('/movie/1')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'TMDB viewer',page.data)
        self.assertIn(b'Wonderful movie!',page.data)
        self.assertIn(b'Sign in to rate',page.data)
        self.assertEqual(self.save().status_code,302)
        self.assertEqual(self.client.post('/movie/1/review/delete').status_code,302)
        self.assertEqual(db.session.query(MovieReview).count(),0)

    def test_rating_only_and_written_review_counts_are_separate(self):
        self.register();self.assertEqual(self.save(4,'').status_code,303)
        page=self.client.get('/movie/1')
        self.assertIn(b'data-rating-count>1<',page.data)
        self.assertIn(b'data-written-count>0<',page.data)
        self.assertIn(b'data-community-average>4.0<',page.data)
        self.client.post('/logout');self.register('another');self.save(2,'The story was disappointing.')
        page=self.client.get('/movie/1')
        self.assertIn(b'data-rating-count>2<',page.data)
        self.assertIn(b'data-written-count>1<',page.data)
        self.assertIn(b'data-community-average>3.0<',page.data)
        self.assertIn(b'another',page.data)
        self.assertIn(b'TMDB viewer',page.data)

    def test_update_duplicate_and_clear_text_do_not_inflate_counts(self):
        self.register();self.save(5,'Loved it!');row=db.session.scalar(select(MovieReview));identity=row.id;created=row.created_at
        self.assertEqual(row.created_at,row.updated_at)
        self.save(5,'Loved it!');self.save(3,'Enjoyed parts of it.')
        self.assertEqual(db.session.query(MovieReview).count(),1)
        db.session.expire_all();row=db.session.get(MovieReview,identity)
        self.assertEqual(row.rating,3);self.assertEqual(row.body,'Enjoyed parts of it.')
        self.assertEqual(row.created_at,created)
        page=self.client.get('/movie/1')
        self.assertIn(b'checked',page.data)
        self.assertIn(b'Enjoyed parts of it.',page.data)
        self.save(4,'   ')
        self.assertEqual(db.session.scalar(select(MovieReview)).body,'')
        self.assertIn(b'data-written-count>0<',self.client.get('/movie/1').data)

    def test_movie_and_author_identity_come_from_server(self):
        self.register()
        response=self.client.post('/movie/1/review',data={'rating':'5','body':'Great film','user_id':999,'movie_id':999,'movie_title':'Forged'})
        self.assertEqual(response.status_code,303)
        row=db.session.scalar(select(MovieReview));user=db.session.scalar(select(User))
        self.assertEqual(row.user_id,user.id);self.assertEqual(row.movie_id,1)
        self.assertEqual(row.movie_title,FILM['title'])

    def test_invalid_rating_and_long_body_do_not_write(self):
        self.register()
        for rating in ('','0','6','-1','4.5','text'):
            with self.subTest(rating=rating):
                self.assertEqual(self.save(rating).status_code,400)
        self.assertEqual(self.save(4,'x'*3001).status_code,400)
        self.assertEqual(db.session.query(MovieReview).count(),0)
        self.assertEqual(self.save(4,'x'*3000).status_code,303)

    def test_public_review_escapes_html_and_is_visible_signed_out(self):
        self.register();self.save(5,'<script>alert("test")</script>\nA good film.');self.client.post('/logout')
        page=self.client.get('/movie/1')
        self.assertIn(b'&lt;script&gt;',page.data)
        self.assertNotIn(b'<script>alert(',page.data)
        self.assertIn(b'abhay',page.data)
        self.assertIn(b'A good film.',page.data)

    def test_delete_only_own_review_and_recalculate(self):
        self.register();self.save(5,'Great film');first=db.session.scalar(select(MovieReview)).id
        self.client.post('/logout');self.register('another');self.save(1,'A dull movie')
        self.assertEqual(self.client.post('/movie/1/review/delete').status_code,303)
        self.assertEqual(db.session.query(MovieReview).count(),1)
        self.assertIsNotNone(db.session.get(MovieReview,first))
        self.assertEqual(self.client.post('/movie/1/review/delete').status_code,404)
        self.assertIn(b'data-community-average>5.0<',self.client.get('/movie/1').data)

    def test_owner_moderation_requires_owner_and_updates_counts(self):
        self.register();self.save();identity=db.session.scalar(select(MovieReview)).id
        self.assertEqual(self.client.post(f'/admin/reviews/{identity}/delete').status_code,403)
        self.app.config['ADMIN_USER_ID']=db.session.scalar(select(User.id))
        self.assertIn(b'Remove as site owner',self._other_users_review())
        self.assertEqual(self.client.post(f'/admin/reviews/{identity}/delete').status_code,303)
        self.assertEqual(self.client.post(f'/admin/reviews/{identity}/delete').status_code,404)

    def _other_users_review(self):
        user=User(username='otherreviewer',password_hash='unused-test-hash');db.session.add(user);db.session.flush()
        db.session.add(MovieReview(user_id=user.id,movie_id=1,movie_title=FILM['title'],rating=4,body='Good film'));db.session.commit()
        return self.client.get('/movie/1').data

    def test_csrf_required_for_publish_delete_and_moderation(self):
        self.register();self.save();identity=db.session.scalar(select(MovieReview)).id
        self.app.config['ADMIN_USER_ID']=db.session.scalar(select(User.id))
        self.app.config['WTF_CSRF_ENABLED']=True
        for path in ('/movie/1/review','/movie/1/review/delete',f'/admin/reviews/{identity}/delete'):
            self.assertEqual(self.client.post(path,data={'rating':4}).status_code,400)
        self.assertEqual(db.session.query(MovieReview).count(),1)

    def test_pagination_ten_per_page_with_full_counts(self):
        for i in range(12):
            user=User(username='reader'+str(i),password_hash='unused');db.session.add(user);db.session.flush()
            db.session.add(MovieReview(user_id=user.id,movie_id=1,movie_title=FILM['title'],rating=4,
                body='Public text '+str(i),created_at=now()-timedelta(days=1),updated_at=now()))
        db.session.commit()
        page=self.client.get('/movie/1')
        self.assertEqual(page.data.count(b'class="audience-review cine-review"'),10)
        self.assertIn(b'data-written-count>12<',page.data)
        self.assertEqual(self.client.get('/movie/1?reviews_page=2').data.count(b'class="audience-review cine-review"'),2)
        self.assertEqual(self.client.get('/movie/1?reviews_page=3').status_code,404)
        self.assertEqual(self.client.get('/movie/1?reviews_page=abc').status_code,400)

    def test_library_lists_own_public_ratings_separate_from_private_history(self):
        self.register();self.save(5,'My public review')
        page=self.client.get('/library')
        self.assertIn(b'Your public movie ratings.',page.data)
        self.assertIn(b'My public review',page.data)
        self.assertIn(b'Your saved analyses.',page.data)
        self.client.post('/logout');self.register('another')
        self.assertNotIn(b'My public review',self.client.get('/library').data)

    def test_database_constraints_and_additive_table_setup(self):
        self.register();user=db.session.scalar(select(User))
        db.session.add(MovieReview(user_id=user.id,movie_id=1,movie_title='Film',rating=8,body=''))
        with self.assertRaises(IntegrityError):db.session.commit()
        db.session.rollback();self.save()
        db.session.add(MovieReview(user_id=user.id,movie_id=1,movie_title='Film',rating=2,body=''))
        with self.assertRaises(IntegrityError):db.session.commit()
        db.session.rollback()
        MovieReview.__table__.drop(db.engine);db.create_all()
        self.assertIsNotNone(db.session.get(User,user.id))

    def test_ratings_are_isolated_per_movie(self):
        self.register();self.save(5,'Excellent first movie')
        with patch('tmdb.detail',return_value=dict(OTHER,id=2)):
            response=self.client.post('/movie/2/review',data={'rating':2,'body':'Disappointing second movie'})
            self.assertEqual(response.status_code,303)
            second=self.client.get('/movie/2')
        first=self.client.get('/movie/1')
        self.assertIn(b'data-rating-count>1<',first.data)
        self.assertIn(b'data-community-average>5.0<',first.data)
        self.assertNotIn(b'Disappointing second movie',first.data)
        self.assertIn(b'data-community-average>2.0<',second.data)
        self.assertNotIn(b'Excellent first movie',second.data)

    def test_save_failure_rolls_back_and_preserves_input(self):
        self.register()
        with patch('community.db.session.commit',side_effect=SQLAlchemyError('private details')):
            response=self.save(4,'Keep this input')
        self.assertEqual(response.status_code,503)
        self.assertIn(b'Keep this input',response.data)
        self.assertNotIn(b'private details',response.data)
        self.assertEqual(db.session.query(MovieReview).count(),0)

if __name__=='__main__':unittest.main()
