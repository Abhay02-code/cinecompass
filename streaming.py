"""Country-specific free discovery and explicitly owner-checked provider links."""
import hashlib
import ipaddress
import re
from datetime import timedelta
from urllib.parse import unquote, urlsplit

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from analytics import is_owner, utc_today
from database import FreeWatchLink
from extensions import db, limiter
from forms import FreeWatchLinkForm
import tmdb

COUNTRIES = {'IN':'India','US':'United States','GB':'United Kingdom','CA':'Canada','AU':'Australia'}
MODES = {'all':'All free offers','free':'Free without ads','ads':'Free with ads'}


def region_value(value=None):
    region = (value if value is not None else request.args.get('watch_region','IN')).strip().upper()
    if region not in COUNTRIES:
        abort(400,'Choose a supported country.')
    return region


def safe_provider_url(value):
    """Public HTTPS movie-page URL. Never fetched by this server; owner attests source."""
    if not isinstance(value,str) or len(value)>1500 or not value.isascii():
        return False
    decoded=value
    for _ in range(3):
        if any(ord(c)<=32 or ord(c)==127 for c in decoded) or '\\' in decoded:
            return False
        decoded=unquote(decoded)
    try:
        parsed=urlsplit(value)
        host=parsed.hostname or ''
        if parsed.scheme!='https' or parsed.username is not None or parsed.password is not None or parsed.port not in (None,443):
            return False
        if not re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}',host):
            return False
        if host.lower().endswith(('.local','.localhost','.internal','.invalid','.test','.example')):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        path=parsed.path.rstrip('/').lower()
        if not path or path in ('/login','/signin','/signup','/register','/search'):
            return False
        return True
    except ValueError:
        return False


def tmdb_watch_url(value,movie_id):
    if not isinstance(value,str):return None
    try:
        parsed=urlsplit(value)
        if (parsed.scheme=='https' and parsed.netloc in ('www.themoviedb.org','themoviedb.org')
                and parsed.path==f'/movie/{movie_id}/watch'):
            return value
    except ValueError:
        pass
    return None


def active_links(region,movie_id=None,kind=None,limit=40):
    query=select(FreeWatchLink).where(FreeWatchLink.region==region,
                                    FreeWatchLink.checked_on<=utc_today(),FreeWatchLink.expires_on>=utc_today())
    if movie_id is not None:query=query.where(FreeWatchLink.movie_id==movie_id)
    if kind in ('free','ads'):query=query.where(FreeWatchLink.kind==kind)
    return db.session.scalars(query.order_by(FreeWatchLink.checked_on.desc(),FreeWatchLink.id.desc()).limit(limit)).all()


def availability(movie_id,region):
    result={'region':region,'country':COUNTRIES[region],'offers':[],'listing_url':None,'error':None}
    try:
        payload=tmdb.watch_providers(movie_id)
        country=payload.get('results',{}).get(region,{})
        result['listing_url']=tmdb_watch_url(country.get('link'),movie_id)
        seen=set()
        for kind in ('free','ads'):
            for item in country.get(kind,[]):
                key=(item.get('provider_id'),kind)
                if key in seen or not isinstance(item.get('provider_id'),int):continue
                seen.add(key)
                result['offers'].append({'name':item.get('provider_name','Streaming provider'),
                    'kind':kind,'logo':item.get('logo_path') if re.fullmatch(r'/[A-Za-z0-9._-]+',item.get('logo_path') or '') else None})
    except tmdb.MovieError:
        result['error']='Streaming availability could not be checked right now. Try again later.'
    return result


def watch_context(movie_id):
    region=region_value()
    return {'watch':availability(movie_id,region),'watch_region':region,'watch_countries':COUNTRIES,
            'direct_watch_links':active_links(region,movie_id)}


def register_streaming(app):
    @app.get('/free-movies')
    @limiter.limit('30 per minute')
    def free_movies():
        region=region_value()
        mode=request.args.get('mode','all')
        if mode not in MODES:abort(400,'Choose a free offer type.')
        try:page=int(request.args.get('page','1'))
        except ValueError:abort(400,'Invalid page number.')
        if not 1<=page<=500:abort(400,'Page must be between 1 and 500.')
        data={'results':[],'total_pages':0};error=None
        try:
            data=tmdb.discover_free(region,mode,page)
            data=dict(data,results=[item for item in data.get('results',[]) if not item.get('adult')])
        except tmdb.MovieError as exc:error=str(exc)
        args={'watch_region':region,'mode':mode}
        return render_template('free_movies.html',data=data,error=error,watch_region=region,
            countries=COUNTRIES,modes=MODES,mode=mode,page=page,
            direct_links=active_links(region,kind=mode),
            previous=url_for('free_movies',page=page-1,**args) if page>1 else None,
            following=url_for('free_movies',page=page+1,**args) if page<min(data.get('total_pages',0),500) else None)

    def admin_page(form,status=200):
        rows=db.session.scalars(select(FreeWatchLink).order_by(FreeWatchLink.id.desc()).limit(100)).all()
        return render_template('manage_watch_links.html',form=form,rows=rows,today=utc_today()),status

    @app.route('/admin/watch-links',methods=['GET','POST'])
    @login_required
    @limiter.limit('30 per minute')
    def manage_watch_links():
        if not is_owner():abort(403)
        form=FreeWatchLinkForm()
        if request.method=='GET':
            candidate=request.args.get('movie_id','')
            if candidate.isascii() and candidate.isdigit() and len(candidate)<11:form.movie_id.data=int(candidate)
            form.region.data=region_value()
        if form.validate_on_submit():
            if not safe_provider_url(form.url.data):
                form.url.errors.append('Use a public HTTPS URL for the exact movie, not a platform homepage, login page or search result.')
                return admin_page(form,400)
            item=tmdb.detail(form.movie_id.data)
            today=utc_today()
            insert=pg_insert if db.engine.dialect.name=='postgresql' else sqlite_insert
            stmt=insert(FreeWatchLink).values(movie_id=form.movie_id.data,movie_title=item.get('title','Untitled')[:300],
                poster_path=item.get('poster_path'),region=form.region.data,provider=form.provider.data,
                kind=form.kind.data,url=form.url.data,url_hash=hashlib.sha256(form.url.data.encode()).hexdigest(),
                checked_on=today,expires_on=today+timedelta(days=6),checked_by=current_user.id)
            db.session.execute(stmt.on_conflict_do_update(index_elements=['movie_id','region','url_hash'],
                set_={name:getattr(stmt.excluded,name) for name in ('movie_title','poster_path','provider','kind','checked_on','expires_on','checked_by')}))
            db.session.commit();flash('Checked link published for 7 UTC calendar days. Recheck it before renewing.')
            return redirect(url_for('manage_watch_links'),code=303)
        return admin_page(form,400 if request.method=='POST' else 200)

    @app.post('/admin/watch-links/<int:link_id>/<action>')
    @login_required
    @limiter.limit('30 per minute')
    def change_watch_link(link_id,action):
        if not is_owner():abort(403)
        if action not in ('renew','delete'):abort(404)
        row=db.session.get(FreeWatchLink,link_id)
        if row is None:abort(404)
        if action=='delete':
            db.session.delete(row);flash('Watch link removed.')
        else:
            if request.form.get('confirmed')!='yes':abort(400,'Recheck the full movie and confirm it is still legally free before renewing.')
            row.checked_on=utc_today();row.expires_on=utc_today()+timedelta(days=6);row.checked_by=current_user.id
            flash('Watch link renewed after your confirmation.')
        db.session.commit()
        return redirect(url_for('manage_watch_links'),code=303)
