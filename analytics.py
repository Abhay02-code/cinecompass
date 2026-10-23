"""First-party, opt-in aggregate analytics. No IPs, query text or account IDs."""
import csv
import hashlib
import hmac
import io
import re
import secrets
from datetime import datetime, timedelta, timezone

import click
from flask import (abort, current_app, flash, make_response, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from itsdangerous import BadData, URLSafeSerializer
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from accounts import safe_next
from database import DailyMetric, DailyVisitor, User
from extensions import db, limiter

CONSENT_COOKIE = 'cc_analytics'
VISITOR_COOKIE = 'cc_visitor'
PAGE_PATHS = {'index':'/', 'movie':'/movie/<id>', 'model_card':'/model',
              'for_you':'/for-you', 'library':'/library', 'about':'/about', 'free_movies':'/free-movies'}
KNOWN_BOTS = re.compile(r'bot|crawler|spider|headless|preview|uptime|monitor', re.I)


def utc_today():
    return datetime.now(timezone.utc).date()


def is_owner():
    identity = current_app.config.get('ADMIN_USER_ID')
    return bool(identity and current_user.is_authenticated and current_user.id == identity)


def privacy_signal():
    return request.headers.get('DNT') == '1' or request.headers.get('Sec-GPC') == '1'


def serializer():
    return URLSafeSerializer(current_app.secret_key, salt='cinecompass-analytics-v1')


def read_visitor():
    try:
        value = serializer().loads(request.cookies.get(VISITOR_COOKIE, ''))
        return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{32}', value) else None
    except BadData:
        return None


def cookie_options():
    return {'secure': current_app.config['SESSION_COOKIE_SECURE'],
            'httponly': True, 'samesite': 'Lax', 'path': '/'}


def increment(day, kind, path):
    dialect = db.engine.dialect.name
    insert = pg_insert if dialect == 'postgresql' else sqlite_insert
    statement = insert(DailyMetric).values(day=day, kind=kind, path=path, count=1)
    db.session.execute(statement.on_conflict_do_update(
        index_elements=['day', 'kind', 'path'], set_={'count': DailyMetric.count + 1}))


def record_usage(response):
    """Only successful, consented operations; never break the original response."""
    if (request.cookies.get(CONSENT_COOKIE) != 'yes' or privacy_signal() or is_owner()
            or KNOWN_BOTS.search(request.headers.get('User-Agent', ''))
            or not 200 <= response.status_code < 300):
        return response
    events = []
    if request.method == 'GET' and response.mimetype == 'text/html' and request.endpoint in PAGE_PATHS:
        events.append(('page_view', PAGE_PATHS[request.endpoint]))
    if request.method == 'GET' and request.endpoint == 'search_suggestions' and 2 <= len(request.args.get('q','').strip()) <= 100:
        events.append(('search_request', '/api/search'))
    if request.method == 'POST' and request.endpoint == 'analyze':
        events.append(('analysis', '/api/analyze'))
    if not events:
        return response
    visitor = read_visitor()
    new_visitor = visitor is None
    visitor = visitor or secrets.token_urlsafe(24)
    # Only a keyed digest of a random browser ID is stored, never the cookie or IP.
    visitor_hash = hmac.new(current_app.secret_key.encode(), visitor.encode(), hashlib.sha256).hexdigest()
    day = utc_today()
    try:
        dialect = db.engine.dialect.name
        if dialect not in ('sqlite', 'postgresql'):
            return response
        insert = pg_insert if dialect == 'postgresql' else sqlite_insert
        db.session.execute(insert(DailyVisitor).values(day=day, visitor_hash=visitor_hash)
                           .on_conflict_do_nothing(index_elements=['day','visitor_hash']))
        for kind, path in events:
            increment(day, kind, path)
        # Small date-indexed deletes keep at most 90 UTC calendar days.
        cutoff = day - timedelta(days=89)
        db.session.execute(delete(DailyMetric).where(DailyMetric.day < cutoff))
        db.session.execute(delete(DailyVisitor).where(DailyVisitor.day < cutoff))
        db.session.commit()
        if new_visitor:
            response.set_cookie(VISITOR_COOKIE, serializer().dumps(visitor), max_age=30*86400, **cookie_options())
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.warning('ANALYTICS_WRITE_FAILED: %s; original request served.', type(exc).__name__)
    return response


def range_days():
    try:
        days = int(request.args.get('days', '30'))
    except ValueError:
        abort(400, 'Choose 7, 30 or 90 days.')
    if days not in (7, 30, 90):
        abort(400, 'Choose 7, 30 or 90 days.')
    return days


def report(days):
    today = utc_today()
    start = today - timedelta(days=days-1)
    totals = {kind: count for kind, count in db.session.execute(
        select(DailyMetric.kind, func.sum(DailyMetric.count))
        .where(DailyMetric.day.between(start,today)).group_by(DailyMetric.kind))}
    visitors = db.session.scalar(select(func.count(distinct(DailyVisitor.visitor_hash)))
                                 .where(DailyVisitor.day.between(start,today))) or 0
    users = db.session.scalar(select(func.count(User.id))) or 0
    new_users = db.session.scalar(select(func.count(User.id)).where(
        User.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
        User.created_at < datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))) or 0
    daily = {}
    for day, kind, count in db.session.execute(select(DailyMetric.day, DailyMetric.kind, func.sum(DailyMetric.count))
            .where(DailyMetric.day.between(start,today)).group_by(DailyMetric.day,DailyMetric.kind)):
        daily.setdefault(day,{})[kind] = count
    unique_daily = dict(db.session.execute(select(DailyVisitor.day,func.count())
                        .where(DailyVisitor.day.between(start,today)).group_by(DailyVisitor.day)).all())
    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        values = daily.get(day,{})
        series.append({'day':day,'visitors':unique_daily.get(day,0),
                       'views':values.get('page_view',0),'searches':values.get('search_request',0),
                       'analyses':values.get('analysis',0)})
    pages = db.session.execute(select(DailyMetric.path,func.sum(DailyMetric.count).label('views'))
             .where(DailyMetric.day.between(start,today), DailyMetric.kind=='page_view')
             .group_by(DailyMetric.path).order_by(func.sum(DailyMetric.count).desc())).all()
    return dict(days=days,start=start,today=today,totals=totals,visitors=visitors,
                users=users,new_users=new_users,series=series,pages=pages,
                peak=max((row['views'] for row in series),default=0) or 1)


def register_analytics(app):
    @app.context_processor
    def analytics_context():
        return {'owner_access': is_owner(), 'analytics_choice': request.cookies.get(CONSENT_COOKIE),
                'analytics_blocked': privacy_signal()}

    app.after_request(record_usage)

    @app.get('/about')
    def about():
        return render_template('about.html')

    @app.get('/privacy')
    def privacy():
        return render_template('privacy.html')

    @app.post('/privacy/analytics')
    @limiter.limit('30 per minute')
    def analytics_consent():
        choice = request.form.get('choice')
        if choice not in ('yes','no'):
            abort(400, 'Choose Allow or Decline.')
        if privacy_signal():
            choice = 'no'
        target = safe_next(request.form.get('next')) or url_for('privacy')
        response = redirect(target)
        response.set_cookie(CONSENT_COOKIE, choice, max_age=365*86400, **cookie_options())
        if choice == 'no':
            response.delete_cookie(VISITOR_COOKIE, **cookie_options())
        flash('Anonymous usage measurement enabled.' if choice=='yes' else 'Anonymous usage measurement is off.')
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @app.get('/admin/analytics')
    @login_required
    def admin_analytics():
        if not is_owner():
            abort(403)
        return render_template('analytics.html', **report(range_days()))

    @app.get('/admin/analytics.csv')
    @login_required
    def analytics_csv():
        if not is_owner():
            abort(403)
        data = report(range_days())
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['UTC date','Approx visitors (opt-in)','Page views (opt-in)',
                         'Autocomplete requests (opt-in)','Analyses (opt-in)'])
        for row in data['series']:
            writer.writerow([row['day'].isoformat(),row['visitors'],row['views'],row['searches'],row['analyses']])
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename="cinecompass-analytics.csv"'
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @app.cli.command('prune-analytics')
    def prune_analytics():
        """Remove analytics older than 90 calendar days, even on idle sites."""
        cutoff = utc_today()-timedelta(days=89)
        db.session.execute(delete(DailyMetric).where(DailyMetric.day<cutoff))
        db.session.execute(delete(DailyVisitor).where(DailyVisitor.day<cutoff))
        db.session.commit()
        click.echo('Analytics retention cleanup complete.')
