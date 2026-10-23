import json
import os
import re
import secrets
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv, dotenv_values
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import cache, csrf, db, limiter, login
from database import User, WatchItem, Analysis, MovieReview
from forms import PreferenceForm
from accounts import register_account_routes, csrf_auth_error, auth_page, next_destination
from forms import RegisterForm, LoginForm
import tmdb
import ml
from analytics import register_analytics
from community import community_context, register_community

ROOT = Path(__file__).resolve().parent
RELEASE = '3.3.0'
load_dotenv(ROOT / '.env', encoding='utf-8-sig')


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(ROOT/'instance'))
    Path(app.instance_path).mkdir(exist_ok=True)
    production = os.getenv('APP_ENV') == 'production'
    secret = os.getenv('SECRET_KEY','')
    if production and (len(secret)<32 or secret.startswith('change')):
        raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters in production.')
    if not secret:
        secret_file = Path(app.instance_path)/'local-secret.txt'
        if not secret_file.exists(): secret_file.write_text(secrets.token_hex(32))
        secret = secret_file.read_text().strip()
    uri = os.getenv('DATABASE_URL','sqlite:///'+str(ROOT/'instance/cinecompass.db'))
    if uri.startswith('postgres://'): uri = uri.replace('postgres://','postgresql+psycopg://',1)
    elif uri.startswith('postgresql://'): uri = uri.replace('postgresql://','postgresql+psycopg://',1)
    if production and uri.startswith('sqlite:'):
        raise RuntimeError('Set DATABASE_URL to PostgreSQL for durable production storage.')
    token = os.getenv('TMDB_READ_TOKEN', '').strip()
    if not token and not production:
        token = (dotenv_values(ROOT / '.env', encoding='utf-8-sig').get('TMDB_READ_TOKEN') or '').strip()
    # Accept a copied Authorization value without sending 'Bearer Bearer ...'.
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('\"', "'"):
        token = token[1:-1].strip()
    admin_identity = os.getenv('ADMIN_USER_ID', '').strip()
    app.config.update(SECRET_KEY=secret, SQLALCHEMY_DATABASE_URI=uri,
                      SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping':True},
                      TMDB_READ_TOKEN=token,
                      ADMIN_USER_ID=int(admin_identity) if re.fullmatch(r'[1-9][0-9]*', admin_identity) else None,
                      MAX_CONTENT_LENGTH=32768, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=production,
                      REMEMBER_COOKIE_HTTPONLY=True, REMEMBER_COOKIE_SAMESITE='Lax',
                      REMEMBER_COOKIE_SECURE=production, REMEMBER_COOKIE_DURATION=timedelta(days=14),
                      WTF_CSRF_TIME_LIMIT=3600)
    if test_config: app.config.update(test_config)
    db.init_app(app); login.init_app(app); csrf.init_app(app); cache.init_app(app); limiter.init_app(app)
    if not app.config.get('TMDB_READ_TOKEN'):
        app.logger.warning('MOVIE_DATA_NOT_CONFIGURED: Set TMDB_READ_TOKEN in this web service Environment and redeploy. No credential was loaded.')
    login.login_view = 'signin'
    login.login_message = 'Please sign in to continue.'

    @login.user_loader
    def user_loader(identity):
        try: return db.session.get(User, int(identity))
        except (ValueError, TypeError): return None

    @app.context_processor
    def context():
        return {'configured':tmdb.configured(), 'genres':tmdb.GENRES, 'release': RELEASE}

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' https://image.tmdb.org; style-src 'self'; script-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if current_user.is_authenticated or response.mimetype == 'text/html':
            response.headers['Cache-Control']='private, no-store, max-age=0'
            response.headers['Pragma']='no-cache'
        return response

    def page_number():
        try: return max(1,min(int(request.args.get('page',1)),500))
        except ValueError: abort(400, 'Invalid page number.')

    def local_redirect():
        # Fixed destinations prevent open redirects after login.
        return redirect(url_for('index'))

    @app.get('/')
    def index():
        query=request.args.get('q','').strip()
        genre=request.args.get('genre','')
        language=request.args.get('language','')
        year=request.args.get('year','').strip()
        sort=request.args.get('sort','popularity.desc')
        if len(query)>100: abort(400,'Movie title must be at most 100 characters.')
        if genre and genre not in {str(k) for k in tmdb.GENRES}: abort(400,'Invalid genre.')
        if language not in ('','en','hi','ta','te','ml','ko','ja','fr','es'): abort(400,'Invalid language.')
        if year and (not year.isdigit() or not 1880<=int(year)<=2100): abort(400,'Invalid year.')
        if sort not in ('popularity.desc','vote_average.desc','primary_release_date.desc'): abort(400,'Invalid sort.')
        page=page_number(); data={'results':[], 'total_pages':0}; error=None
        if tmdb.configured():
            try:
                data=tmdb.search(query,page,year) if query else tmdb.discover(page,genre,language,sort)
            except tmdb.MovieError as exc: error=str(exc)
        else:
            error = 'Movie search is temporarily unavailable. Please try again later.'
        args=request.args.to_dict(); args.pop('page',None)
        previous=url_for('index',page=page-1,**args) if page>1 else None
        following=url_for('index',page=page+1,**args) if page<min(data.get('total_pages',0),500) else None
        return render_template('index.html', data=data, query=query, genre=genre, language=language,
                               year=year, sort=sort, page=page, previous=previous, following=following,error=error)

    @app.get('/api/search')
    @limiter.limit('120 per minute')
    def search_suggestions():
        query = request.args.get('q', '').strip()
        if len(query) > 100:
            return jsonify(error='Movie title must be at most 100 characters.'), 400
        if len(query) < 2:
            return jsonify(results=[])
        year = request.args.get('year', '').strip()
        if year and (not year.isdigit() or not 1880 <= int(year) <= 2100):
            return jsonify(error='Enter a valid release year.'), 400
        try:
            data = tmdb.search(query, year=year or None)
        except tmdb.MovieError as exc:
            return jsonify(error=str(exc)), exc.status
        results = []
        seen = set()
        for item in data.get('results', []):
            identity = item.get('id')
            if not isinstance(identity, int) or identity in seen or item.get('adult'):
                continue
            seen.add(identity)
            results.append({'id': identity, 'title': item.get('title', 'Untitled'),
                            'year': (item.get('release_date') or '')[:4],
                            'poster_path': item.get('poster_path'),
                            'rating': item.get('vote_average'),
                            'url': url_for('movie', movie_id=identity),
                            'genres': [tmdb.GENRES[g] for g in item.get('genre_ids', []) if g in tmdb.GENRES][:2]})
            if len(results) == 8:
                break
        return jsonify(results=results)

    @app.get('/movie/<int:movie_id>')
    def movie(movie_id, community_form=None, status=200):
        item=tmdb.detail(movie_id)
        reviews, total, truncated, warning=[],0,0,None
        try:
            reviews,total,truncated=tmdb.reviews(movie_id)
            for review in reviews: review['sentiment']=ml.analyze(review['content'])
        except tmdb.MovieError as exc: warning=str(exc)
        pool,warnings=tmdb.candidates(movie_id)
        recs=ml.recommend([item],pool,exclude=[movie_id])
        saved=None
        if current_user.is_authenticated:
            saved=db.session.scalar(select(WatchItem).where(WatchItem.user_id==current_user.id, WatchItem.movie_id==movie_id))
        trailer=next((v['key'] for v in item.get('videos',{}).get('results',[]) if v.get('site')=='YouTube' and v.get('type')=='Trailer' and re.fullmatch(r'[\w-]+',v.get('key',''))),None)
        return render_template('movie.html',movie=item,reviews=reviews,summary=ml.aggregate(reviews),total=total,
                               truncated=truncated,warning=warning,recs=recs,rec_warnings=warnings,saved=saved,trailer=trailer,
                               **community_context(movie_id,community_form)), status

    register_account_routes(app)
    register_analytics(app)
    register_community(app, movie)

    @app.post('/watchlist/<int:movie_id>')
    @login_required
    @limiter.limit('30 per minute')
    def save_movie(movie_id):
        action=request.form.get('action','save')
        if action not in ('save','like','unlike','remove'): abort(400,'Invalid action.')
        row=db.session.scalar(select(WatchItem).where(WatchItem.user_id==current_user.id,WatchItem.movie_id==movie_id))
        if action=='remove':
            if row: db.session.delete(row)
        elif row:
            if action in ('like','unlike'): row.liked=action=='like'
        else:
            item=tmdb.detail(movie_id)
            db.session.add(WatchItem(user_id=current_user.id,movie_id=movie_id,title=item['title'],
                                    poster_path=item.get('poster_path'),release_date=item.get('release_date'),liked=action=='like'))
        try: db.session.commit()
        except IntegrityError:
            db.session.rollback(); flash('Movie is already saved.')
        return redirect(url_for('library'))

    @app.route('/library',methods=['GET','POST'])
    @login_required
    def library():
        form=PreferenceForm()
        if form.validate_on_submit():
            current_user.genres=','.join(form.genres.data); db.session.commit(); flash('Preferences saved.'); return redirect(url_for('library'))
        if request.method=='GET': form.genres.data=(current_user.genres or '').split(',')
        items=db.session.scalars(select(WatchItem).where(WatchItem.user_id==current_user.id).order_by(WatchItem.created_at.desc())).all()
        history=db.session.scalars(select(Analysis).where(Analysis.user_id==current_user.id).order_by(Analysis.id.desc()).limit(30)).all()
        public_reviews=db.session.scalars(select(MovieReview).where(MovieReview.user_id==current_user.id).order_by(MovieReview.updated_at.desc()).limit(20)).all()
        return render_template('library.html',items=items,history=history,form=form,public_reviews=public_reviews)

    @app.get('/for-you')
    @login_required
    @limiter.limit('15 per minute')
    def for_you():
        liked=db.session.scalars(select(WatchItem).where(WatchItem.user_id==current_user.id,WatchItem.liked.is_(True)).order_by(WatchItem.created_at.desc()).limit(3)).all()
        all_ids=db.session.scalars(select(WatchItem.movie_id).where(WatchItem.user_id==current_user.id)).all()
        preferred=[int(x) for x in (current_user.genres or '').split(',') if x.isdigit()]
        seeds,pool,warnings=[],[],[]
        for saved in liked:
            try:
                seeds.append(tmdb.detail(saved.movie_id)); candidates,partial=tmdb.candidates(saved.movie_id); pool.extend(candidates); warnings.extend(partial)
            except tmdb.MovieError as exc: warnings.append(str(exc))
        try: pool.extend(tmdb.discover(genre='|'.join(map(str,preferred)) if preferred else None).get('results',[]))
        except tmdb.MovieError as exc: warnings.append(str(exc))
        recs=ml.recommend(seeds,pool,preferred,all_ids)
        return render_template('for_you.html',recs=recs,warnings=list(set(warnings)),seed_count=len(seeds))

    @app.post('/api/analyze')
    @limiter.limit('30 per minute')
    def analyze():
        data=request.get_json(silent=True)
        content=data.get('text') if isinstance(data,dict) else None
        if not isinstance(content,str) or len(content.strip())<3: return jsonify(error='Enter at least 3 characters of English review text.'),400
        if len(content)>5000: return jsonify(error='Maximum review length is 5,000 characters.'),400
        if data.get('save') not in (None,True,False): return jsonify(error='Invalid save option.'),400
        if data.get('save') and not current_user.is_authenticated: return jsonify(error='Sign in to save analysis.'),401
        result=ml.analyze(content.strip())
        if data.get('save'):
            db.session.add(Analysis(user_id=current_user.id,text=content.strip(),label=result['label'],positive_probability=result['positive_probability']))
            db.session.commit()
        return jsonify(**result,saved=bool(data.get('save')))

    @app.post('/history/<int:analysis_id>/delete')
    @login_required
    def delete_analysis(analysis_id):
        row=db.session.scalar(select(Analysis).where(Analysis.id==analysis_id,Analysis.user_id==current_user.id))
        if not row: abort(404)
        db.session.delete(row); db.session.commit(); return redirect(url_for('library'))

    @app.get('/model')
    def model_card(): return render_template('model.html',metrics=ml.metrics())

    @app.get('/api/status')
    def deployment_status():
        response = jsonify(version=RELEASE, movie_data_configured=tmdb.configured(),
                           shared_account_database=db.engine.url.drivername.startswith('postgresql'))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/health')
    def health():
        db.session.execute(text('SELECT 1'))
        return jsonify(status='ok')

    @app.errorhandler(tmdb.MovieError)
    def movie_error(exc): return render_template('error.html',message=str(exc),status=exc.status),exc.status

    @app.errorhandler(CSRFError)
    def csrf_error(exc):
        if request.endpoint in ('signin', 'register'):
            return csrf_auth_error()
        message='Your form expired or is missing its security token. Refresh the page and try again.'
        if request.path.startswith('/api/'): return jsonify(error=message),400
        return render_template('error.html',message=message,status=400),400

    for code in (400,403,404,413,429,500):
        def handler(exc):
            code=getattr(exc,'code',500)
            if code == 429 and request.endpoint in ('signin', 'register'):
                registering = request.endpoint == 'register'
                form = RegisterForm(formdata=None) if registering else LoginForm(formdata=None)
                form.username.data = request.form.get('username', '').strip().lower()[:40]
                return auth_page(form, registering, next_destination(), 'Too many attempts. Wait a minute and try again.', 429)
            message=getattr(exc,'description','Something went wrong.') if code!=500 else 'An unexpected error occurred. Please try again.'
            if request.path.startswith('/api/'): return jsonify(error=message),code
            return render_template('error.html',message=message,status=code),code
        app.register_error_handler(code,handler)
    return app

app=create_app()

if __name__=='__main__':
    with app.app_context(): db.create_all()
    app.run(host='127.0.0.1',port=int(os.getenv('PORT',5000)),debug=False)
