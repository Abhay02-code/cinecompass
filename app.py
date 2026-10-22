import os
import re
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from extensions import cache, csrf, db, limiter, login
from database import User, WatchItem, Analysis
from forms import RegisterForm, LoginForm, PreferenceForm

import tmdb
import ml


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def create_app(test_config=None):
    app = Flask(
        __name__,
        instance_path=str(ROOT / "instance"),
    )

    Path(app.instance_path).mkdir(exist_ok=True)

    production = os.getenv("APP_ENV") == "production"
    secret = os.getenv("SECRET_KEY", "").strip()

    if production and (
        len(secret) < 32 or secret.startswith("change")
    ):
        raise RuntimeError(
            "Set SECRET_KEY to a random value of at least "
            "32 characters in production."
        )

    if not secret:
        secret_file = (
            Path(app.instance_path) / "local-secret.txt"
        )

        if not secret_file.exists():
            secret_file.write_text(secrets.token_hex(32))

        secret = secret_file.read_text().strip()

    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + str(ROOT / "instance/cinecompass.db"),
    )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    if production and database_url.startswith("sqlite:"):
        raise RuntimeError(
            "Set DATABASE_URL to PostgreSQL in production."
        )

    app.config.update(
        SECRET_KEY=secret,
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
        },
        TMDB_READ_TOKEN=os.getenv(
            "TMDB_READ_TOKEN", ""
        ).strip(),
        MAX_CONTENT_LENGTH=32768,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        WTF_CSRF_TIME_LIMIT=3600,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)

    login.login_view = "signin"
    login.login_message = "Please sign in to continue."

    @login.user_loader
    def user_loader(identity):
        try:
            return db.session.get(User, int(identity))
        except (ValueError, TypeError):
            return None

    @app.context_processor
    def context():
        return {
            "configured": tmdb.configured(),
            "genres": tmdb.GENRES,
        }

    @app.after_request
    def security_headers(response):
        response.headers[
            "X-Content-Type-Options"
        ] = "nosniff"

        response.headers["X-Frame-Options"] = "DENY"

        response.headers["Referrer-Policy"] = (
            "strict-origin-when-cross-origin"
        )

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' https://image.tmdb.org; "
            "style-src 'self'; "
            "script-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        )

        if current_user.is_authenticated:
            response.headers["Cache-Control"] = "no-store"

        return response

    def page_number():
        try:
            return max(
                1,
                min(int(request.args.get("page", 1)), 500),
            )
        except ValueError:
            abort(400, description="Invalid page number.")

    def home_redirect():
        return redirect(url_for("index"))

    # --------------------------------------------------
    # Home / movie catalogue
    # --------------------------------------------------

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()
        genre = request.args.get("genre", "")
        language = request.args.get("language", "")
        year = request.args.get("year", "").strip()
        sort = request.args.get(
            "sort", "popularity.desc"
        )

        if len(query) > 100:
            abort(
                400,
                description=(
                    "Movie title must be at most "
                    "100 characters."
                ),
            )

        valid_genres = {
            str(genre_id) for genre_id in tmdb.GENRES
        }

        if genre and genre not in valid_genres:
            abort(400, description="Invalid genre.")

        valid_languages = (
            "",
            "en",
            "hi",
            "ta",
            "te",
            "ml",
            "ko",
            "ja",
            "fr",
            "es",
        )

        if language not in valid_languages:
            abort(400, description="Invalid language.")

        if year and (
            not year.isdigit()
            or not 1880 <= int(year) <= 2100
        ):
            abort(400, description="Invalid year.")

        valid_sorts = (
            "popularity.desc",
            "vote_average.desc",
            "primary_release_date.desc",
        )

        if sort not in valid_sorts:
            abort(400, description="Invalid sort.")

        page = page_number()

        data = {
            "results": [],
            "total_pages": 0,
        }

        error = None

        if tmdb.configured():
            try:
                if query:
                    data = tmdb.search(query, page, year)
                else:
                    data = tmdb.discover(
                        page,
                        genre,
                        language,
                        sort,
                    )
            except tmdb.MovieError as exc:
                error = str(exc)

        pagination_args = {
            "q": query,
            "genre": genre,
            "language": language,
            "year": year,
            "sort": sort,
        }

        previous = None
        following = None

        if page > 1:
            previous = url_for(
                "index",
                page=page - 1,
                **pagination_args,
            )

        total_pages = min(
            data.get("total_pages", 0), 500
        )

        if page < total_pages:
            following = url_for(
                "index",
                page=page + 1,
                **pagination_args,
            )

        return render_template(
            "index.html",
            data=data,
            query=query,
            genre=genre,
            language=language,
            year=year,
            sort=sort,
            page=page,
            previous=previous,
            following=following,
            error=error,
        )

    # --------------------------------------------------
    # Live search suggestions
    # --------------------------------------------------

    @app.get("/api/search")
    @limiter.limit("120 per minute")
    def search_suggestions():
        query = request.args.get("q", "").strip()
        year = request.args.get("year", "").strip()

        if len(query) < 2:
            return jsonify(results=[])

        if len(query) > 100:
            return jsonify(
                error=(
                    "Movie title must be at most "
                    "100 characters."
                )
            ), 400

        if year and (
            not year.isdigit()
            or not 1880 <= int(year) <= 2100
        ):
            return jsonify(
                error="Enter a valid release year."
            ), 400

        try:
            data = tmdb.search(
                query,
                year=year or None,
            )
        except tmdb.MovieError as exc:
            return jsonify(error=str(exc)), exc.status

        movies = []
        seen = set()

        for item in data.get("results", []):
            movie_id = item.get("id")

            if (
                not isinstance(movie_id, int)
                or movie_id in seen
                or item.get("adult")
            ):
                continue

            seen.add(movie_id)

            genre_names = [
                tmdb.GENRES[genre_id]
                for genre_id in (
                    item.get("genre_ids") or []
                )
                if genre_id in tmdb.GENRES
            ][:2]

            movies.append(
                {
                    "id": movie_id,
                    "title": item.get(
                        "title", "Untitled"
                    ),
                    "year": (
                        item.get("release_date") or ""
                    )[:4],
                    "poster_path": item.get(
                        "poster_path"
                    ),
                    "rating": item.get(
                        "vote_average"
                    ),
                    "genres": genre_names,
                    "url": url_for(
                        "movie",
                        movie_id=movie_id,
                    ),
                }
            )

            if len(movies) == 8:
                break

        return jsonify(results=movies)

    # --------------------------------------------------
    # Movie details and reviews
    # --------------------------------------------------

    @app.get("/movie/<int:movie_id>")
    def movie(movie_id):
        item = tmdb.detail(movie_id)

        reviews = []
        total = 0
        truncated = 0
        warning = None

        try:
            reviews, total, truncated = tmdb.reviews(
                movie_id
            )

            for review in reviews:
                review["sentiment"] = ml.analyze(
                    review["content"]
                )
        except tmdb.MovieError as exc:
            warning = str(exc)

        pool, recommendation_warnings = (
            tmdb.candidates(movie_id)
        )

        recommendations = ml.recommend(
            [item],
            pool,
            exclude=[movie_id],
        )

        saved = None

        if current_user.is_authenticated:
            saved = db.session.scalar(
                select(WatchItem).where(
                    WatchItem.user_id
                    == current_user.id,
                    WatchItem.movie_id == movie_id,
                )
            )

        trailer = next(
            (
                video["key"]
                for video in item.get(
                    "videos", {}
                ).get("results", [])
                if video.get("site") == "YouTube"
                and video.get("type") == "Trailer"
                and re.fullmatch(
                    r"[\w-]+",
                    video.get("key", ""),
                )
            ),
            None,
        )

        return render_template(
            "movie.html",
            movie=item,
            reviews=reviews,
            summary=ml.aggregate(reviews),
            total=total,
            truncated=truncated,
            warning=warning,
            recs=recommendations,
            rec_warnings=recommendation_warnings,
            saved=saved,
            trailer=trailer,
        )

    # --------------------------------------------------
    # Accounts
    # --------------------------------------------------

    @app.route(
        "/register", methods=["GET", "POST"]
    )
    @limiter.limit(
        "10 per minute", methods=["POST"]
    )
    def register():
        if current_user.is_authenticated:
            return home_redirect()

        form = RegisterForm()

        if form.validate_on_submit():
            user = User(
                username=(
                    form.username.data.strip().lower()
                ),
                password_hash=generate_password_hash(
                    form.password.data
                ),
            )

            db.session.add(user)

            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()

                form.username.errors.append(
                    "That username is already taken."
                )
            else:
                session.clear()
                login_user(user)

                flash(
                    "Welcome! Choose your favourite "
                    "genres in your library."
                )

                return redirect(
                    url_for("library")
                )

        return render_template(
            "auth.html",
            form=form,
            title="Create your account",
            register=True,
        )

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit(
        "10 per minute", methods=["POST"]
    )
    def signin():
        if current_user.is_authenticated:
            return home_redirect()

        form = LoginForm()

        if form.validate_on_submit():
            username = (
                form.username.data.strip().lower()
            )

            user = db.session.scalar(
                select(User).where(
                    User.username == username
                )
            )

            if user and check_password_hash(
                user.password_hash,
                form.password.data,
            ):
                session.clear()
                login_user(user)

                return home_redirect()

            form.password.errors.append(
                "Invalid username or password."
            )

        return render_template(
            "auth.html",
            form=form,
            title="Welcome back",
            register=False,
        )

    @app.post("/logout")
    @login_required
    def signout():
        logout_user()
        session.clear()

        return home_redirect()

    # --------------------------------------------------
    # Watchlist and likes
    # --------------------------------------------------

    @app.post("/watchlist/<int:movie_id>")
    @login_required
    @limiter.limit("30 per minute")
    def save_movie(movie_id):
        action = request.form.get(
            "action", "save"
        )

        if action not in (
            "save",
            "like",
            "unlike",
            "remove",
        ):
            abort(
                400,
                description="Invalid action.",
            )

        row = db.session.scalar(
            select(WatchItem).where(
                WatchItem.user_id
                == current_user.id,
                WatchItem.movie_id == movie_id,
            )
        )

        if action == "remove":
            if row:
                db.session.delete(row)

        elif row:
            if action in ("like", "unlike"):
                row.liked = action == "like"

        else:
            item = tmdb.detail(movie_id)

            db.session.add(
                WatchItem(
                    user_id=current_user.id,
                    movie_id=movie_id,
                    title=item["title"],
                    poster_path=item.get(
                        "poster_path"
                    ),
                    release_date=item.get(
                        "release_date"
                    ),
                    liked=action == "like",
                )
            )

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Movie is already saved.")

        return redirect(url_for("library"))

    # --------------------------------------------------
    # Library and preferences
    # --------------------------------------------------

    @app.route(
        "/library", methods=["GET", "POST"]
    )
    @login_required
    def library():
        form = PreferenceForm()

        if form.validate_on_submit():
            current_user.genres = ",".join(
                form.genres.data
            )

            db.session.commit()
            flash("Preferences saved.")

            return redirect(
                url_for("library")
            )

        if request.method == "GET":
            form.genres.data = (
                current_user.genres or ""
            ).split(",")

        items = db.session.scalars(
            select(WatchItem)
            .where(
                WatchItem.user_id
                == current_user.id
            )
            .order_by(
                WatchItem.created_at.desc()
            )
        ).all()

        history = db.session.scalars(
            select(Analysis)
            .where(
                Analysis.user_id
                == current_user.id
            )
            .order_by(Analysis.id.desc())
            .limit(30)
        ).all()

        return render_template(
            "library.html",
            items=items,
            history=history,
            form=form,
        )

    # --------------------------------------------------
    # Personalised recommendations
    # --------------------------------------------------

    @app.get("/for-you")
    @login_required
    @limiter.limit("15 per minute")
    def for_you():
        liked = db.session.scalars(
            select(WatchItem)
            .where(
                WatchItem.user_id
                == current_user.id,
                WatchItem.liked.is_(True),
            )
            .order_by(
                WatchItem.created_at.desc()
            )
            .limit(3)
        ).all()

        saved_ids = db.session.scalars(
            select(WatchItem.movie_id).where(
                WatchItem.user_id
                == current_user.id
            )
        ).all()

        preferred_genres = [
            int(value)
            for value in (
                current_user.genres or ""
            ).split(",")
            if value.isdigit()
        ]

        seeds = []
        pool = []
        warnings = []

        for saved in liked:
            try:
                seeds.append(
                    tmdb.detail(saved.movie_id)
                )

                candidates, partial_warnings = (
                    tmdb.candidates(
                        saved.movie_id
                    )
                )

                pool.extend(candidates)
                warnings.extend(
                    partial_warnings
                )

            except tmdb.MovieError as exc:
                warnings.append(str(exc))

        try:
            genre_filter = (
                "|".join(
                    map(str, preferred_genres)
                )
                if preferred_genres
                else None
            )

            discovery = tmdb.discover(
                genre=genre_filter
            )

            pool.extend(
                discovery.get("results", [])
            )

        except tmdb.MovieError as exc:
            warnings.append(str(exc))

        recommendations = ml.recommend(
            seeds,
            pool,
            preferred_genres,
            saved_ids,
        )

        return render_template(
            "for_you.html",
            recs=recommendations,
            warnings=list(dict.fromkeys(warnings)),
            seed_count=len(seeds),
        )

    # --------------------------------------------------
    # Review sentiment analysis
    # --------------------------------------------------

    @app.post("/api/analyze")
    @limiter.limit("30 per minute")
    def analyze():
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify(
                error="Send a valid review."
            ), 400

        content = data.get("text")
        save = data.get("save", False)

        if (
            not isinstance(content, str)
            or len(content.strip()) < 3
        ):
            return jsonify(
                error=(
                    "Enter at least 3 characters "
                    "of English review text."
                )
            ), 400

        if len(content) > 5000:
            return jsonify(
                error=(
                    "Maximum review length is "
                    "5,000 characters."
                )
            ), 400

        if save is None:
            save = False

        if not isinstance(save, bool):
            return jsonify(
                error="Invalid save option."
            ), 400

        if (
            save
            and not current_user.is_authenticated
        ):
            return jsonify(
                error="Sign in to save analysis."
            ), 401

        result = ml.analyze(content.strip())

        if save:
            db.session.add(
                Analysis(
                    user_id=current_user.id,
                    text=content.strip(),
                    label=result["label"],
                    positive_probability=result[
                        "positive_probability"
                    ],
                )
            )

            db.session.commit()

        return jsonify(
            **result,
            saved=save,
        )

    @app.post(
        "/history/<int:analysis_id>/delete"
    )
    @login_required
    def delete_analysis(analysis_id):
        row = db.session.scalar(
            select(Analysis).where(
                Analysis.id == analysis_id,
                Analysis.user_id
                == current_user.id,
            )
        )

        if not row:
            abort(404)

        db.session.delete(row)
        db.session.commit()

        return redirect(url_for("library"))

    # --------------------------------------------------
    # Model information and health check
    # --------------------------------------------------

    @app.get("/model")
    def model_card():
        return render_template(
            "model.html",
            metrics=ml.metrics(),
        )

    @app.get("/health")
    def health():
        db.session.execute(text("SELECT 1"))

        return jsonify(status="ok")

    # --------------------------------------------------
    # Error handlers
    # --------------------------------------------------

    @app.errorhandler(tmdb.MovieError)
    def movie_error(exc):
        if request.path.startswith("/api/"):
            return jsonify(
                error=str(exc)
            ), exc.status

        return render_template(
            "error.html",
            message=str(exc),
            status=exc.status,
        ), exc.status

    @app.errorhandler(CSRFError)
    def csrf_error(exc):
        message = (
            "Your form expired or is missing "
            "its security token. Refresh the "
            "page and try again."
        )

        if request.path.startswith("/api/"):
            return jsonify(
                error=message
            ), 400

        return render_template(
            "error.html",
            message=message,
            status=400,
        ), 400

    def http_error(exc):
        status = getattr(exc, "code", 500)

        if status == 500:
            message = (
                "An unexpected error occurred. "
                "Please try again."
            )
        else:
            message = getattr(
                exc,
                "description",
                "Something went wrong.",
            )

        if request.path.startswith("/api/"):
            return jsonify(
                error=message
            ), status

        return render_template(
            "error.html",
            message=message,
            status=status,
        ), status

    for status in (400, 404, 413, 429, 500):
        app.register_error_handler(
            status,
            http_error,
        )

    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", 5000)),
        debug=False,
    )