For creator credit and private analytics setup (release 3.2.0), start with **OWNER_ANALYTICS.md**.

> Account update 3.2.0: read AUTH_FIX.md for signup/login improvements and Render account persistence requirements.

> Version 3.2.0: public setup instructions have been removed. Read RENDER_FIX.md if Render search is not working. Configure TMDB_READ_TOKEN on the actual web service; .env is local only. /api/status identifies this release.

# CineCompass — movie discovery, sentiment & recommendations

A complete runnable portfolio project with a live TMDB catalogue, a bundled trained movie-review classifier, content-based recommendations, accounts and persistent watchlists. No five-film demo catalogue, synthetic audience reviews, paid LLM or runtime model download.

## Start here — VS Code on Windows

1. Install **Python 3.11** (3.10–3.13 supported) and **Git** if needed. Check **Add Python to PATH** during installation.
2. Extract this ZIP. Open the **cinecompass** folder in VS Code. The open folder must directly contain `app.py`, `requirements.txt` and `start.bat`.
3. Open Terminal → New Terminal and run:

```powershell
.\start.bat
```

The launcher creates `.venv`, installs dependencies, creates `.env` only if missing, initializes SQLite and starts the app. It stops on setup errors instead of running missing executables.

4. Open **http://127.0.0.1:5000**.
5. Add the TMDB token as described below, then stop with Ctrl+C and run `start.bat` again.

### If Python is not detected

Run `py --list` and `python --version`. If Python 3.11 is missing but another supported version exists, the launcher uses your installed default Python 3. If neither command works, install Python from https://www.python.org/downloads/windows/, close/reopen VS Code, then retry. If your default Python is newer than 3.13, create the environment explicitly with a supported installed version, e.g. `py -3.11 -m venv .venv`. Remove an incompatible `.venv` before recreating it (only that generated environment, not your code).

### Manual Windows setup

Run **one command at a time**, and continue only when it succeeds:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe app.py
```

Only copy `.env.example` on first setup: do not overwrite an existing token file.

macOS/Linux: `sh start.sh` (Python 3.10–3.13 installed).

## Required: connect the live movie catalogue

Movie data needs a developer credential. It is not possible to bundle someone else's secret API token into your public GitHub project.

1. Sign up at https://www.themoviedb.org/.
2. Open https://www.themoviedb.org/settings/api and apply for API access.
3. Copy the **API Read Access Token** (bearer token), not the shorter v3 API key.
4. In `.env` next to `app.py`, set:

```dotenv
TMDB_READ_TOKEN=paste_your_api_read_access_token_here
APP_ENV=development
```

5. Restart the server. Live discovery loads after the service is restarted with a valid credential.

With no token, visitors see a short movie-service unavailable message; the trained review analyser, accounts and model results still work. It never presents mock movie data as real. Keep `.env` private: it is excluded from Git. Invalid tokens or network/API errors show clear messages. TMDB and its image CDN must be reachable from the client/server network.

## Updated search and review experience

Type at least two characters in the movie search box. Live suggestions show the movie poster, title, year, genres and rating. Click a suggestion to open that exact movie’s reviews, sentiment summary, story and related films. Arrow keys + Enter select a suggestion; Escape dismisses the list. The search button still opens full search results and year filtering.

Suggestions require your TMDB token and network access. Loading, no-match and service-error states are displayed honestly; no sample catalogue is substituted. The redesigned movie page shows review excerpts immediately instead of hiding every review behind a collapsed panel.

## Features

- Live autocomplete while typing, plus title/year search, pagination and selection of the exact movie.
- Discover by genre, original language (including Hindi, Tamil, Telugu and Malayalam) and sort order. Filters apply to discovery; search uses title/year.
- Posters, story, cast, genre, runtime, TMDB rating and YouTube trailer link when available.
- Real English review sample from TMDB, with per-review sentiment and aggregate counts.
- English review analysis by a trained TF-IDF + Logistic Regression model bundled in `models/`.
- Content-based recommendation ranking written in this project, using plot similarity, genre overlap and rating.
- Username/password accounts, hashed passwords, CSRF protection, rate limits and secure deployment cookies.
- Save/remove watchlist entries, like/unlike movies, choose genre preferences, and get personalised picks.
- Opt-in private analysis history, with deletion. Plain analysis is not stored.
- SQLite locally, PostgreSQL on Render. Local and deployment configuration are separate.
- Model metrics page, reproducible training script, tests and GitHub Actions CI.

## Push to GitHub

Create an **empty** GitHub repository, e.g. `cinecompass` (do not add another README there). In VS Code's terminal from this project folder:

```bash
git init
git add .
git status
git commit -m "Build CineCompass movie discovery and ML app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cinecompass.git
git push -u origin main
```

Replace YOUR_USERNAME. Before committing, verify `.env`, `instance/` data and `.venv/` are not staged. **Do commit `models/sentiment.joblib` and `models/metrics.json`**; they are required at runtime. The model is small enough for ordinary Git. Complete GitHub authentication when prompted.

For future updates:

```bash
git add .
git commit -m "Describe your change"
git push
```

## Deploy on Render — recommended Blueprint route

The project requires **a web service plus PostgreSQL** for persistent accounts and watchlists. Render plan availability, retention and pricing can change; review the service/database plan selections before confirming creation.

1. Push the project to GitHub.
2. In https://dashboard.render.com/, choose **New → Blueprint**.
3. Connect the repository and select the branch.
4. Render reads the root `render.yaml`, which defines the web service and PostgreSQL database.
5. Enter your `TMDB_READ_TOKEN` when prompted. A random `SECRET_KEY` is generated automatically. `DATABASE_URL` is wired to the database's internal connection string.
6. Review the web/database plans, then create the resources.
7. Wait for the database and web service to deploy. Open your Render web URL.

Database tables are initialized with `python init_db.py` before Gunicorn starts. The included model is loaded for inference; training is not run during deployment.

### Manual Render setup

Create a Render PostgreSQL database and a Python Web Service in the same region. Connect the GitHub repository. Leave Root Directory empty if app.py is at the repository root.

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `python init_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120` |
| Health check | `/health` |
| `PYTHON_VERSION` | `3.11.11` |
| `APP_ENV` | `production` |
| `TMDB_READ_TOKEN` | Your API Read Access Token |
| `SECRET_KEY` | Random secret of at least 32 characters |
| `DATABASE_URL` | Render PostgreSQL **Internal Database URL** |

Generate a secret locally with:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Do not copy a placeholder secret into production. Production refuses SQLite because an ephemeral Render filesystem would lose account data. It also requires a strong secret. Local `.env` is not uploaded; use Render Environment settings. Do not use `python app.py` as the production start command.

Check `/health` after deployment. It checks process/database connectivity, not TMDB availability. Try a search, registration, saved movie and sentiment analysis to verify all integrations. This package has not been deployed to your Render account automatically.

Official deployment references: https://render.com/docs/deploy-flask, https://render.com/docs/blueprint-spec and https://render.com/docs/postgresql-creating-connecting.

## ML experiment and model card

See `models/metrics.json` and the in-app **The model** page for exact measured results. The training data is the Pang & Lee **sentence polarity v1.0** movie-review dataset:
https://www.cs.cornell.edu/people/pabo/movie-review-data/.

The script removes exact case-insensitive duplicates, then performs a stratified 80/20 train/test split with random seed 42. The vocabulary is fit only on the training partition. The classifier uses TF-IDF unigrams/bigrams and Logistic Regression. A SHA-256 hash records the exact downloaded archive. Dataset texts are not redistributed in this ZIP.

To reproduce the experiment (requires network access):

```powershell
.\.venv\Scripts\python.exe scripts\train_sentiment.py
```

Or with an already-downloaded archive:

```powershell
.\.venv\Scripts\python.exe scripts\train_sentiment.py --archive C:\path\rt-polaritydata.tar.gz
```

Short reviews (up to 50 words) use VADER English negation-aware rules; mixed or weak sentiment abstains as Uncertain. Longer reviews use the trained classifier: positive estimate >=0.60 → Positive; <=0.40 → Negative; between → Uncertain. The reported benchmark applies only to the original classifier, before short-review routing. See MODEL_CARD.md for exact thresholds. **Uncertain is not a learned neutral class.** Reported test accuracy uses the standard 0.50 boundary; do not confuse it with the three display buckets. Probabilities are uncalibrated. Dataset performance is not accuracy on all real-world reviews. The old English sentence dataset may overlap by film/author across the random split, and differs from modern full-length reviews. Hindi/Hinglish, sarcasm and nuanced reviews are unsupported or unreliable. Do not claim the model is trained on TMDB or IMDb full reviews.

Only load the bundled trusted joblib model. Joblib/pickle files from strangers can execute code. Keep scikit-learn and numeric dependencies pinned when using a serialized model.

## Recommendation method

TMDB supplies candidate metadata, not the final ranking. For a movie, candidates come from its similar-movies endpoint and a discovery page. For personalised results, candidate pools come from up to three liked movies and a genre-filtered discovery page (at most roughly 140 fetched records, before deduplication).

Our engine fits TF-IDF over seed/candidate plots and genre tokens and computes cosine similarity. Ranking score:

`0.75 × maximum seed similarity + 0.20 × genre Jaccard overlap + 0.05 × rating / 10`

Saved IDs and duplicate candidates are excluded. Genre overlap uses seed genres plus user preferences. With no liked seeds, recommendations are genre/rating discovery picks. Scores are relative ranking heuristics, not enjoyment probabilities. This engine does not search every TMDB movie at once, and does not implement collaborative filtering.

## Audience sentiment scope

Up to three pages / 60 available English TMDB reviews are analysed. Duplicates are removed, and each review is truncated to 12,000 characters. Counts and truncation information are shown. Empty reviews produce no estimate. These are an available review sample, not the opinion of all viewers. TMDB numeric ratings and text polarity are separate signals.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover configuration, actual bundled sentiment inference, accounts, login/logout, password hashing, watchlist/preferences, history access isolation, CSRF, input validation, recommendation ranking/deduplication, mocked live search/details, API/network errors, and escaping/headers. Tests do not need TMDB credentials. GitHub Actions runs the suite on pushes and PRs. External TMDB connectivity and a deployed Render PostgreSQL instance still require your credentials and deployment verification.

## Structure

```text
app.py                    Flask app factory, routes, auth and validation
extensions.py             Database, CSRF, rate limits, cache, login
database.py               User, WatchItem and Analysis tables
forms.py                  Validated account and preference forms
tmdb.py                   Bounded/cached live movie API requests
ml.py                     Bundled inference and custom recommendations
init_db.py                Idempotent initial table creation
models/                   Trained model and measured metrics
scripts/train_sentiment.py Reproducible training pipeline
templates/                Server-rendered responsive pages
static/                   CSS, JavaScript and attribution logo
tests/                    Integration tests
.github/workflows/        GitHub Actions CI
render.yaml               Web service + PostgreSQL Blueprint
start.bat / start.sh       Local launchers
```

## Operational notes

This is a complete initial portfolio application, not a claim of enterprise readiness. Accounts have no email verification, password recovery, admin portal or account deletion UI. Sign-in supports optional remembered sessions and safe local return URLs. Review text can be deleted; account deletion currently requires an operator/database action. Deploy only with a database plan/backup policy suitable for the data you intend to retain.

Rate limits and API caches use per-process memory; the supplied command deliberately uses one worker. Limits reset on restart and are not distributed. On Render, the remote-address limiter may group clients behind a proxy; for a larger deployment use a trusted-proxy configuration plus shared Redis rate-limit/cache storage. Do not blindly trust arbitrary forwarded headers. The bundled configuration does not enable proxy trust.

`db.create_all()` initializes this initial schema; it is not a migration system for future column changes. Add Alembic/Flask-Migrate before shipping schema updates against an existing database. Local SQLite data is not automatically copied into Render PostgreSQL.

## Troubleshooting

- **Movie service unavailable:** set TMDB_READ_TOKEN in `.env`, then restart. On Render, use its Environment settings.
- **No suitable Python runtime:** the launcher does not require exactly 3.11; run `py --list` and install/use Python 3.10–3.13.
- **Module not found:** use `.venv\Scripts\python.exe`, not a different Python interpreter. In VS Code select this environment via Python: Select Interpreter.
- **Invalid token:** use the API Read Access Token (bearer), not v3 key.
- **No reviews:** some titles have no English TMDB reviews. Personal review analysis still works.
- **Cannot reach TMDB:** check provider availability and server/network access; the application cannot bypass upstream connectivity restrictions.
- **Form expired:** refresh the page and retry; CSRF tokens expire after one hour.
- **Render fails early:** inspect logs for a missing secret/database URL, root directory mismatch or database connectivity failure.
- **Gunicorn on Windows:** use `start.bat` locally; Gunicorn is for the Linux Render deployment.
- **Port 5000 busy:** set `$env:PORT="5001"` before starting and open http://127.0.0.1:5001.

## Credits and terms

Movie metadata, artwork and review content come from TMDB. This product uses the TMDB API but is not endorsed or certified by TMDB. The unmodified approved TMDB logo is included in the model/credits page. See https://developer.themoviedb.org/docs/faq for attribution and API terms. Developer access is intended for non-commercial use under TMDB terms; obtain appropriate permission for commercial use.

Sentiment dataset: Bo Pang and Lillian Lee, *Seeing stars: Exploiting class relationships for sentiment categorization with respect to rating scales*, ACL 2005. Review text copyrights remain with their original owners. Dataset download is solely through the original source. Dependencies retain their respective licenses. Project source code is under the MIT license; this does not relicense external data, posters, logos or dataset/model usage rights.

### Autocomplete endpoint

`GET /api/search?q=inter` returns up to 8 non-adult, deduplicated movie matches, with title, year, poster, genres, rating and detail URL. Queries under two characters return an empty list without calling TMDB. Queries over 100 characters return 400; upstream errors return JSON with an appropriate status. Browser input is debounced by 300 ms and outdated requests are cancelled/ignored. No API token is exposed in the response.

The regression suite now includes autocomplete validation, deduplication, service errors and visible review excerpts. UI workflows are checked with isolated API fixtures; that is not verification of your live credentials.

## Creator & owner dashboard

Built by Abhay Kumar Aditya. Public /about and /privacy pages; private /admin/analytics. Set ADMIN_USER_ID to your own existing LIVE account ID to grant dashboard access. No automatic admin account is created. Usage analytics requires visitor opt-in; counts are estimates, not verified people. See OWNER_ANALYTICS.md for installation, database table creation, privacy and metric definitions.
