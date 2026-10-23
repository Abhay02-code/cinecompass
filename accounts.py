"""Account forms, safe login redirects and session lifecycle."""
from hashlib import sha256
from urllib.parse import unquote, urlsplit
import secrets

from flask import flash, g, redirect, render_template, request, session, url_for, current_app
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from database import User
from extensions import db, limiter
from forms import LoginForm, RegisterForm

# Match the password-hashing work for unknown and known usernames.
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(24))


def safe_next(target):
    """Only local paths; reject external, encoded and backslash redirects."""
    if not isinstance(target, str) or not target or len(target) > 2048:
        return None
    target = target.strip()
    checked = target
    for _ in range(3):
        if any(ord(c) < 32 or ord(c) == 127 for c in checked) or '\\' in checked:
            return None
        try:
            parts = urlsplit(checked)
        except ValueError:
            return None
        if parts.scheme or parts.netloc or not checked.startswith('/') or checked.startswith('//'):
            return None
        if parts.path in ('/login', '/register', '/logout'):
            return None
        decoded = unquote(checked)
        if decoded == checked:
            break
        checked = decoded
    # Refuse ambiguous nesting beyond the checks above.
    if '%' in checked.split('?', 1)[0]:
        return None
    return target


def next_destination():
    return safe_next(request.form.get('next_url') or request.args.get('next'))


def auth_rate_key():
    username = request.form.get('username', '').strip().lower()[:40]
    digest = sha256(username.encode('utf-8')).hexdigest()[:20]
    return f'{request.remote_addr}:{digest}'


def auth_page(form, registering, destination, message=None, status=200):
    form.next_url.data = destination or ''
    return render_template(
        'auth.html', form=form, register=registering,
        title='Create your account' if registering else 'Welcome back',
        next_url=destination, auth_message=message,
    ), status


def csrf_auth_error():
    """Issue a fresh form without echoing or retaining a submitted password."""
    registering = request.endpoint == 'register'
    session.pop('csrf_token', None)
    g.pop('csrf_token', None)
    form = RegisterForm(formdata=None) if registering else LoginForm(formdata=None)
    form.username.data = request.form.get('username', '').strip().lower()[:40]
    return auth_page(
        form, registering, next_destination(),
        message='This form expired. Enter your password again and retry. Allow cookies for this site if it keeps happening.',
        status=400,
    )


def register_account_routes(app):
    @app.route('/register', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', key_func=auth_rate_key, methods=['POST'])
    def register():
        destination = next_destination()
        if current_user.is_authenticated:
            return redirect(destination or url_for('library'))
        form = RegisterForm()
        if form.validate_on_submit():
            user = User(username=form.username.data, password_hash=generate_password_hash(form.password.data))
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.username.errors.append('This username is taken. Choose another, or sign in if this is your account.')
                return auth_page(form, True, destination, status=409)
            except SQLAlchemyError as exc:
                db.session.rollback()
                current_app.logger.error('ACCOUNT_DATABASE_FAILED: %s during registration.', type(exc).__name__)
                return auth_page(form, True, destination, 'Accounts are temporarily unavailable. Please try again shortly.', 503)
            session.clear()
            login_user(user, remember=False)
            flash('Your account is ready. You are now signed in.')
            return redirect(destination or url_for('library'))
        return auth_page(form, True, destination, status=400 if request.method == 'POST' else 200)

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', key_func=auth_rate_key, methods=['POST'])
    def signin():
        destination = next_destination()
        if current_user.is_authenticated:
            return redirect(destination or url_for('library'))
        form = LoginForm()
        if form.validate_on_submit():
            try:
                user = db.session.scalar(select(User).where(User.username == form.username.data))
            except SQLAlchemyError as exc:
                db.session.rollback()
                current_app.logger.error('ACCOUNT_DATABASE_FAILED: %s during login.', type(exc).__name__)
                return auth_page(form, False, destination, 'Accounts are temporarily unavailable. Please try again shortly.', 503)
            try:
                valid = check_password_hash(user.password_hash if user else DUMMY_HASH, form.password.data)
            except (ValueError, TypeError):
                valid = False
            if user and valid:
                session.clear()
                login_user(user, remember=bool(form.remember.data))
                flash('You are signed in.')
                return redirect(destination or url_for('library'))
            form.password.errors.append('Invalid username or password. Check your CineCompass username and try again.')
            return auth_page(form, False, destination, status=401)
        return auth_page(form, False, destination, status=400 if request.method == 'POST' else 200)

    @app.post('/logout')
    @login_required
    def signout():
        logout_user()
        # Preserve Flask-Login's instruction to delete the remember cookie.
        clear_remember = session.get('_remember')
        session.clear()
        if clear_remember:
            session['_remember'] = clear_remember
        flash('You have signed out.')
        return redirect(url_for('index'))
