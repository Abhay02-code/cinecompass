# Account and sentiment update — release 3.3.0

## Changes

- Username whitespace/case is normalised consistently before signup and login validation.
- Clear signup, duplicate-username, wrong-password and confirmation messages.
- Separate Sign in / Create account tabs, password show/hide controls and appropriate autofill.
- Safe return to the requested movie/library page after signing in. External redirect targets are rejected.
- Optional Keep me signed in using Flask-Login's signed remember cookie.
- Logout clears both the session and remember cookie.
- Expired/invalid sign-in forms render a fresh protected form instead of a generic dead-end error page. Passwords are not echoed into the refreshed HTML.
- HTML forms are not cached, avoiding stale CSRF tokens from cached login pages.
- Submitting twice is prevented in the browser; buttons reset after navigation/retry.
- Account database failures show a short retry message; details remain in server logs.

Existing usernames, password hashes and database schema are unchanged. No database deletion or migration is required by this patch. The movie autocomplete/public setup-screen fixes from the previous release are included.

## Apply to the EXISTING project

Extract the ZIP in Downloads to a folder named `cinecompass-community-update-v6`.
Keep your existing CineCompass repository open in VS Code, then run from its terminal:

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\cinecompass-community-update-v6\apply_update.py"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe init_db.py
git add .
git commit -m "Fix accounts sentiment and movie search"
git push
```

The updater backs up the old code in .cinecompass-backup (ignored by Git). It preserves .env, the Git repository, models and database files. It does not push or deploy by itself. In Render, deploy the latest commit if automatic deployment is disabled.

## Render configuration needed for working accounts

The deployed web service must use:

- APP_ENV=production
- DATABASE_URL pointing at your persistent PostgreSQL database
- SECRET_KEY set to one fixed, random value of at least 32 characters

Generate SECRET_KEY once and keep that value across restarts and deployments. Changing it logs existing sessions out. Do not post the secret, database URL or user passwords in chat.

Accounts created on your local SQLite database are NOT automatically in the Render PostgreSQL database. Create an account on the live website first, then sign in there with that CineCompass username. TMDB login credentials are separate. If previous accounts were stored on an ephemeral filesystem and lost, this code cannot recover them; recover a database backup if one exists.

The initial table setup command must still run before the server starts:

```text
python init_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

## Verify after deploying

Open `/api/status` on your live service. The release should be 3.3.0. `shared_account_database: true` indicates PostgreSQL is configured (not proof of reachability); `/health` checks an actual database connection. No credentials are exposed by either endpoint.

1. Create a new account on the LIVE site using a 3–40 character username and a 10–128 character password.
2. Confirm you arrive signed in at My library.
3. Sign out, then sign in with the same username/password.
4. Try a wrong password and then correct it; the form should remain usable.
5. Select Keep me signed in only on your own device. Sign out should remove remembered access.
6. From a movie's Watchlist link, sign in; you should return to that movie.

Username matching is case-insensitive; passwords are case-sensitive and spaces are preserved. This release still has no email-based password reset. It does not add Google sign-in or email login.

## Verification scope

Run `python -m unittest discover -s tests -v` in the virtual environment. The suite covers signup validation, duplicate users, username normalisation, wrong credentials, redirect safety, remember-cookie restoration/logout, CSRF recovery, cache headers, database-error responses, invalid sessions and app-restart persistence with a shared database/secret. Production PostgreSQL and your actual Render settings require verification on your deployed service.

## Sentiment repair included

The screenshot's “this movie is too good yar” previously returned Negative; it now returns Positive. Short English reviews (up to 50 words) use VADER's lexicon/negation handling. “not good” is Negative, “not bad” Positive. Reviews with both positive and negative components abstain as Uncertain, as do short texts without clear sentiment. Longer reviews retain the trained TF-IDF classifier and its abstention band. These are transparent heuristics, not perfect language understanding; sarcasm and Hindi/Hinglish remain unreliable.

The result UI and saved history no longer display the baseline classifier's probability as confidence in the combined result. Existing API probability fields remain baseline-only for compatibility; probability_source explicitly identifies them. No database migration is needed. Old saved analysis labels are preserved; re-analyse old text to obtain the new result.

The original 78.48% test accuracy applies only to the original classifier, not the new combined rules. The model card explains this. No live review benchmark is claimed.

## Completed local checks

43 automated tests passed, covering accounts, CSRF, data isolation, sentiment regression, movie search, reviews, saved movies and recommendation ranking. Browser checks passed for signup, signin retries, remember/logout, return redirects, expired forms, autocomplete keyboard selection, movie reviews, recommendations, sentiment submissions and mobile layout. Movie API calls in these checks were mocked; your actual Render database, token and TMDB connectivity are not validated by those local tests.
