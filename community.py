"""Public first-party movie ratings, kept separate from TMDB reviews/votes."""
import math
from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from analytics import is_owner
from database import MovieReview, User, now
from extensions import db, limiter
from forms import MovieReviewForm
import tmdb


PER_PAGE = 10


def community_context(movie_id, form=None):
    own = None
    if current_user.is_authenticated:
        own = db.session.scalar(select(MovieReview).where(
            MovieReview.movie_id == movie_id, MovieReview.user_id == current_user.id))
    if form is None:
        form = MovieReviewForm(formdata=None)
        if own:
            form.rating.data = own.rating
            form.body.data = own.body
    base = MovieReview.movie_id == movie_id
    ratings, average = db.session.execute(select(func.count(MovieReview.id), func.avg(MovieReview.rating)).where(base)).one()
    written = db.session.scalar(select(func.count(MovieReview.id)).where(base, MovieReview.body != '')) or 0
    distribution = dict(db.session.execute(select(MovieReview.rating, func.count()).where(base).group_by(MovieReview.rating)).all())
    try:
        page = int(request.args.get('reviews_page','1'))
    except ValueError:
        abort(400,'Invalid community review page.')
    pages = max(1, math.ceil(written/PER_PAGE))
    if page < 1 or page > pages:
        abort(404,'Community review page not found.')
    rows = db.session.execute(select(MovieReview,User.username).join(User,MovieReview.user_id==User.id)
            .where(base, MovieReview.body != '')
            .order_by(MovieReview.updated_at.desc(), MovieReview.id.desc())
            .offset((page-1)*PER_PAGE).limit(PER_PAGE)).all()
    return {'community':dict(ratings=ratings, average=round(float(average),1) if average is not None else None,
                            written=written,distribution=distribution,rows=rows,page=page,pages=pages),
            'community_form':form,'own_review':own}


def register_community(app, render_movie):
    @app.post('/movie/<int:movie_id>/review')
    @login_required
    @limiter.limit('10 per minute', key_func=lambda: 'review:'+current_user.get_id())
    def publish_review(movie_id):
        form = MovieReviewForm()
        if not form.validate_on_submit():
            return render_movie(movie_id, community_form=form, status=400)
        # Validate movie identity/title with the provider; never trust client author/title/ID fields.
        item = tmdb.detail(movie_id)
        dialect = db.engine.dialect.name
        insert = pg_insert if dialect == 'postgresql' else sqlite_insert
        timestamp = now()
        statement = insert(MovieReview).values(user_id=current_user.id,movie_id=movie_id,
            movie_title=item.get('title','Untitled')[:300],rating=form.rating.data,body=form.body.data,
            created_at=timestamp,updated_at=timestamp)
        try:
            db.session.execute(statement.on_conflict_do_update(index_elements=['user_id','movie_id'],
                set_={'rating':statement.excluded.rating,'body':statement.excluded.body,
                      'movie_title':statement.excluded.movie_title,'updated_at':statement.excluded.updated_at}))
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.warning('COMMUNITY_REVIEW_SAVE_FAILED: %s',type(exc).__name__)
            flash('Your rating could not be saved. Please retry shortly.')
            return render_movie(movie_id, community_form=form, status=503)
        flash('Your public CineCompass rating has been saved.' if not form.body.data else 'Your public CineCompass rating and review have been saved.')
        return redirect(url_for('movie',movie_id=movie_id,_anchor='community'),code=303)

    @app.post('/movie/<int:movie_id>/review/delete')
    @login_required
    @limiter.limit('10 per minute', key_func=lambda: 'review-delete:'+current_user.get_id())
    def delete_own_review(movie_id):
        row = db.session.scalar(select(MovieReview).where(MovieReview.movie_id==movie_id,MovieReview.user_id==current_user.id))
        if row is None:
            abort(404,'You have no rating for this movie.')
        db.session.delete(row)
        db.session.commit()
        flash('Your CineCompass rating and written review have been deleted.')
        return redirect(url_for('movie',movie_id=movie_id,_anchor='community'),code=303)

    @app.post('/admin/reviews/<int:review_id>/delete')
    @login_required
    @limiter.limit('30 per minute')
    def moderate_review(review_id):
        if not is_owner():
            abort(403)
        row = db.session.get(MovieReview,review_id)
        if row is None:
            abort(404)
        movie_id = row.movie_id
        db.session.delete(row)
        db.session.commit()
        flash('The community rating and review were removed.')
        return redirect(url_for('movie',movie_id=movie_id,_anchor='community'),code=303)
