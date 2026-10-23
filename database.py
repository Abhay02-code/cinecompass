from datetime import datetime, timezone
from flask_login import UserMixin
from extensions import db


def now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.Text, nullable=False)
    genres = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime(timezone=True), default=now)


class WatchItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    movie_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(300), nullable=False)
    poster_path = db.Column(db.String(300))
    release_date = db.Column(db.String(20))
    liked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    __table_args__ = (db.UniqueConstraint('user_id', 'movie_id'),)


class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    label = db.Column(db.String(30), nullable=False)
    positive_probability = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)


class DailyMetric(db.Model):
    """Anonymous counters by UTC day and fixed route, with no query strings."""
    day = db.Column(db.Date, primary_key=True)
    kind = db.Column(db.String(30), primary_key=True)
    path = db.Column(db.String(80), primary_key=True)
    count = db.Column(db.Integer, nullable=False, default=0)


class DailyVisitor(db.Model):
    day = db.Column(db.Date, primary_key=True)
    visitor_hash = db.Column(db.String(64), primary_key=True)


class MovieReview(db.Model):
    """One public rating, with optional written review, per account/movie."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    movie_id = db.Column(db.Integer, nullable=False, index=True)
    movie_title = db.Column(db.String(300), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        db.UniqueConstraint('user_id', 'movie_id', name='uq_movie_review_user_movie'),
        db.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_movie_review_rating'),
    )


class FreeWatchLink(db.Model):
    """Owner-checked full-movie links; expire unless explicitly checked again."""
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, nullable=False, index=True)
    movie_title = db.Column(db.String(300), nullable=False)
    poster_path = db.Column(db.String(300))
    region = db.Column(db.String(2), nullable=False)
    provider = db.Column(db.String(80), nullable=False)
    kind = db.Column(db.String(8), nullable=False)
    url = db.Column(db.Text, nullable=False)
    url_hash = db.Column(db.String(64), nullable=False)
    checked_on = db.Column(db.Date, nullable=False)
    expires_on = db.Column(db.Date, nullable=False, index=True)
    checked_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('movie_id','region','url_hash',name='uq_free_watch_movie_region_url'),
        db.CheckConstraint("kind IN ('free','ads')",name='ck_free_watch_kind'),
    )
