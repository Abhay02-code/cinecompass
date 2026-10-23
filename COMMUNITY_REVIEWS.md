# CineCompass public movie ratings & reviews — release 3.4.0

## What visitors see

Open a movie and choose CineCompass / Rate this movie. A new community section shows:

- The CineCompass average star rating out of 5.
- The number of CineCompass accounts that rated this specific movie.
- A separate count of written reviews, with author username, stars, date and public text.
- A 1–5 star distribution and paginated written reviews (10 per page).

TMDB's original audience reviews, reported vote totals, score out of 10 and existing sentiment summary remain in their own clearly labelled section. CineCompass contributions are stored locally in your application database; they are not submitted to TMDB and do not change TMDB's votes or review text.

## How users contribute

1. Search for a movie and open its detail page.
2. Click Rate this movie. Sign in if prompted; signing in returns to the movie's rating form.
3. Choose 1–5 stars. A written review is optional (maximum 3,000 characters).
4. Click Publish rating & review. Your username, stars and any review text become public.
5. Return later to update the same contribution or delete it. My library also lists your latest 20 public ratings with edit/delete links.

One account can rate each movie once. Editing/updating a rating does not add another vote. Blank/whitespace review text is treated as rating-only and is excluded from the written-review count. Changing 5 stars to 3 recalculates the average. Deleting a contribution removes its rating and text from the counts. These are account contributions, not verified movie-ticket buyers; multiple accounts can still be created by one person.

Example: 12 accounts leave ratings and only 7 write text → 12 ratings · 7 written reviews. TMDB votes remain separate. Private sentiment analysis does NOT publish a community review, and publishing a review does not automatically save it to private analysis history.

## Apply to your EXISTING project

Extract the ZIP to Downloads/cinecompass-free-movies-v7. Open your existing repository in VS Code and run from its terminal:

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\cinecompass-free-movies-v7\apply_update.py"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe init_db.py
git add .
git commit -m "Add public movie ratings reviews and community counts"
git push
```

The installer backs up overwritten code and preserves .env, .git, models and existing database files. All previous account, search, sentiment, creator-credit and analytics fixes are included. Do not run the app from the patch's files folder.

A NEW movie_review table is added by init_db.py. Existing tables/columns are not altered, reset or deleted. Existing users, watchlists, private history and analytics remain. Keep database backups as normal; do not delete your database to apply this feature.

## Deploy on Render

Open the cinecompass-2 WEB SERVICE. Use Manual Deploy → Deploy latest commit if needed. Check the new commit message above in Events (not an old commit or a restart of older code).

Keep the existing Start Command:

```bash
python init_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

This command runs on Render, not Windows PowerShell. Table initialization must run before the new app serves movie pages.

Keep your existing valid TMDB_READ_TOKEN, fixed SECRET_KEY, persistent PostgreSQL DATABASE_URL, APP_ENV=production and PYTHON_VERSION=3.11.11. If you configured ADMIN_USER_ID=1 for your existing live account, keep it unchanged. No new API key or service is required.

After Live, open https://cinecompass-2.onrender.com/api/status and check version 3.4.0. Hard-refresh the movie page (Ctrl+Shift+R). Movie data still depends on working TMDB access; local reviews require the application database.

## Owner moderation

The configured owner account can see Remove as site owner on OTHER users' written reviews. It deletes that contribution (stars and text) from the application database. It cannot delete original TMDB content. Users can delete only their own contribution; all write/delete actions require login and CSRF protection. Text is rendered as escaped plain text, not executable HTML. Rating-only contributions have no written-review card; their author can manage them from My library / the movie form.

## Verify after deployment

1. Open a movie and note the TMDB reviews/score.
2. Sign in with your own CineCompass account. Publish 5 stars and a short review.
3. Confirm CineCompass shows 1 rating / 1 written review if nobody else has contributed yet; the original TMDB content remains.
4. Open Incognito while signed out: the published username, stars and review should be visible, but posting requires sign-in.
5. Edit to 3 stars: the count stays the same; the average changes.
6. Remove only the text and save: the rating remains, and written-review count decreases.
7. Delete your contribution: both counts/average update. Test with a second account to confirm one user's edit does not change another's review.

The dashboard starts from actual stored contributions: no fake votes or reviews are bundled. Figures in development/browser checks are isolated test data, not production data.

## Local verification

71 automated tests passed locally, including per-movie isolation, rating-only vs written counts, averages, duplicate/update behavior, author identity, validation, escaping, pagination, own-only deletion, owner moderation, CSRF, save rollback, additive database setup, and all prior account/movie/analytics/sentiment tests. Browser checks covered sign-in return to rating form, posting, editing, rating-only updates, deletion, moderation, counts, preserving TMDB reviews and mobile layout. Provider calls were mocked in local tests; your actual Render PostgreSQL/TMDB access still needs live verification.
