# Creator credit & private analytics — CineCompass 3.3.0

This code-only update includes the previous account/search/sentiment fixes. It adds:

- Public footer credit: Built by Abhay Kumar Aditya, GitHub link, About link and author metadata.
- /about: your introduction, project purpose, technologies and source-code links. No LinkedIn URL was guessed; add yours to templates/about.html if desired.
- /privacy: clear analytics choice and description of collection, account data and operational logs.
- /admin/analytics: private owner dashboard with 7/30/90 UTC day ranges, approximate visitors, page views, autocomplete requests, analyses, account counts, daily graph, page categories and CSV download.

## 1. Apply to your existing VS Code project

Extract the ZIP to Downloads/cinecompass-community-update-v6. In the terminal of your EXISTING project (the folder containing app.py and .git), run:

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\cinecompass-community-update-v6\apply_update.py"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe init_db.py
git add .
git commit -m "Add creator credit and private owner analytics"
git push
```

init_db.py creates the two NEW analytics tables; it does not delete or reset existing account/watchlist/history tables. No existing columns were changed. The updater backs up replaced code and preserves .env, .git, models and database files. Do not run the application from the files folder inside the patch ZIP; apply it to your existing repository.

## 2. Deploy the NEW commit on Render

Open the cinecompass-2 WEB SERVICE linked to Abhay02-code/cinecompass, branch main. Deploy latest commit. A start-command change alone may redeploy an old commit: check the commit description in Events. Use:

Build Command:

```text
pip install -r requirements.txt
```

Start Command (Render only, not Windows PowerShell):

```bash
python init_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

Keep APP_ENV=production, PYTHON_VERSION=3.11.11, valid TMDB_READ_TOKEN, a FIXED strong SECRET_KEY and persistent PostgreSQL DATABASE_URL. Do not replace the secret or database with placeholders. Environment variables belong to the WEB SERVICE. Render's Production dashboard label does not set APP_ENV.

Wait for Live. https://cinecompass-2.onrender.com/api/status should show version 3.3.0. The flags only indicate configuration, not verified provider access. /health checks the database connection. The About link and footer credit appear without admin configuration.

## 3. Give ONLY YOUR account dashboard access

1. Sign in to your own account on the LIVE website, or create it there first. Local SQLite accounts do not automatically exist in the Render PostgreSQL database.
2. Open My library. Near the page heading, read Your Account ID. Use the ID from YOUR LIVE ACCOUNT, not another account or a guess.
3. Render → cinecompass-2 → Environment → Add Environment Variable:
   - Key: ADMIN_USER_ID
   - Value: the numeric Account ID you just read (digits only, no quotes).
4. Save and deploy the change. Keep SECRET_KEY and DATABASE_URL unchanged.
5. Sign in as that same account. The Analytics navigation link appears. Open https://cinecompass-2.onrender.com/admin/analytics.

No account is an owner by default. The first registered account and a user named owner/admin receive NO automatic special access. ADMIN_USER_ID matches an existing authenticated database account; it is not a second password and is never accepted from a URL/form. Other accounts get 403; signed-out visitors are redirected to sign in. CSV downloads use the same protection. Your own account ID is visible only in your signed-in library. The dashboard does not list other usernames or passwords.

For LOCAL testing, set ADMIN_USER_ID in your local .env using your LOCAL account's ID, restart app.py, and sign in. To revoke owner access, remove ADMIN_USER_ID in Render and redeploy.

## 4. Understand the numbers

| Dashboard metric | Meaning |
| --- | --- |
| Approx. visitors | Distinct opted-in browser identifiers in the selected dates. Not verified people. |
| Page views | Successful loads of discover, movie, model, recommendations, library and About pages after opt-in. Reloads count again. |
| Autocomplete requests | Successful /api/search requests with at least 2 query characters. Typing one title can generate several requests; this is NOT the number of completed searches or people. |
| Reviews analysed | Successful opted-in /api/analyze submissions. Repeated submissions count again; automatically analysed TMDB reviews are excluded. |
| Total registered accounts | All database accounts, including owner/test accounts; independent of analytics consent. |
| New accounts | Accounts created in the selected UTC dates. |

Daily visitors are not added together to calculate period visitors; returning browsers are deduplicated across the selected dates while their identifier remains the same. Multiple devices, deleted/expired cookies and unrecognised bots affect estimates. Analytics starts with this deployment; historical traffic cannot be reconstructed. A zero dashboard at first is expected.

## 5. Check measurement with an independent browser

1. Keep your owner account signed in in the normal browser.
2. Open an Incognito window as a visitor, choose Allow on the optional analytics notice, then visit About/Discover.
3. With working TMDB configuration, type a title and choose a movie. Submit one English review such as "this movie is good".
4. Refresh the owner dashboard. Visitor/page/action counters should increase. Your signed-in owner browsing is excluded.
5. In Incognito, open Privacy & choices → Turn off analytics. Future actions should not increment usage counters. DNT/GPC privacy signals also prevent collection.
6. Try /admin/analytics in the signed-out window: it should require login. A different signed-in account must get 403.

## Privacy & storage

No third-party analytics subscription or API key is needed. Usage analytics stores fixed route categories and counts plus a keyed digest of a random browser identifier. It does NOT store IP addresses, account IDs, search text, movie IDs, review text or referrers. The application stores account/watchlist data, private saved analyses and user-published movie ratings/reviews separately. Published movie reviews are public account contributions; see COMMUNITY_REVIEWS.md. Hosting/server access logs are separate and can contain request details, as disclosed on /privacy.

Analytics is off until allowed. The preference cookie lasts 1 year; the random visitor cookie lasts 30 days. Cookies are HttpOnly, SameSite=Lax and Secure in production. DNT and GPC override consent. Decline deletes the visitor cookie and stops future collection. Prior anonymous data remains until retention cleanup.

Only the most recent 90 UTC calendar days are kept after a counted request or explicit cleanup. On an idle site data remains until cleanup executes. To clean up manually (local terminal, or a scheduled environment with the same database and secret):

```powershell
.\.venv\Scripts\python.exe -m flask --app app prune-analytics
```

The analytics tables use PostgreSQL/SQLite atomic upserts to avoid lost increments under concurrent requests. Analytics write failure does not block the main request; check ANALYTICS_WRITE_FAILED logs. PostgreSQL persistence and retention operational scheduling are your hosting responsibilities.

## Verification

57 automated tests passed locally. Run `python -m unittest discover -s tests -v` in the environment. Tests cover access control, consent/CSRF, opt-out, browser deduplication, privacy-signal/bot exclusions, retention, CSV/date ranges, no sensitive analytics columns, existing account preservation, and existing account/movie/sentiment behavior. Browser checks cover opt-in/out, owner navigation, dashboard, CSV, About and mobile layout. Movie provider calls in local checks are mocked; your Render secrets and real PostgreSQL/TMDB access still require live verification.
