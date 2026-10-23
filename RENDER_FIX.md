For account problems, follow AUTH_FIX.md. This release includes the previous movie-data repair.

# Render repair — version 3.3.0

Two separate issues caused the screenshot:

1. The public site displayed the older green frontend rather than the updated autocomplete interface.
2. Its missing-token setup panel means the running web service did not load TMDB_READ_TOKEN. A local .env is ignored by Git and does not configure Render.

This patch includes the complete current frontend and search endpoint; removes developer setup instructions from public pages; adds safe unavailable/error states, image fallbacks and versioned assets; and adds /api/status to identify an old deployment. It does not contain an API token, database or user account data.

## Apply to the existing GitHub project

Extract the repair ZIP to a folder named cinecompass-community-update-v6 in Downloads.
Keep your existing repository open in VS Code. From its terminal (the directory containing app.py):

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\cinecompass-community-update-v6\apply_update.py"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
git add .
git commit -m "Fix deployed movie search and remove public setup screen"
git push
```

The updater backs up changed files in .cinecompass-backup (ignored by Git), copies the patch into the current project, and preserves .env, .git, models and database files. Review git status before committing. It does not push or deploy on its own. Applying the code cannot supply a missing Render secret.

## Configure the actual web service

In Render, open the **cinecompass-2 web service** whose URL is shown in your screenshot. Do not add the token to the PostgreSQL service or only your local computer.

Environment → add/update:

- TMDB_READ_TOKEN: your valid API Read Access Token (no placeholder).
- PYTHON_VERSION: 3.11.11.
- Keep APP_ENV=production, SECRET_KEY and DATABASE_URL configured as before.

Save and rebuild/deploy. If the latest commit did not deploy, select Manual Deploy → Deploy latest commit (or clear build cache and deploy if needed). Confirm the latest commit hash matches GitHub.

The Render Environment label “Production” in the dashboard does not itself set APP_ENV=production. Keep the actual environment variable configured.

## Verify the deployment

Open https://cinecompass-2.onrender.com/api/status.

Expected after applying the patch AND adding the credential:

```json
{"version":"3.3.0","movie_data_configured":true,"shared_account_database":true}
```

True only means a non-empty credential was loaded; it does not prove the token is valid. Then open:
https://cinecompass-2.onrender.com/api/search?q=interstellar

Expected: a JSON results array containing movie matches. A 404 on /api/status means old code is still running. A false flag means the web service is missing its secret. A 503 with the flag true indicates the provider rejected the credential or is unavailable; inspect Render logs. No token value is returned by the status endpoint.

Optional terminal check:

```powershell
.\.venv\Scripts\python.exe scripts\check_deployment.py https://cinecompass-2.onrender.com
```

After this works, open the homepage, press Ctrl+Shift+R and type at least two letters. Select a suggestion to open movie details, audience reviews and sentiment. The new release uses the purple interface, not the older green setup screen.

## Server-only log messages

- MOVIE_DATA_NOT_CONFIGURED: TMDB_READ_TOKEN was not loaded by this service.
- MOVIE_DATA_AUTH_FAILED: TMDB returned 401/403; correct/regenerate the credential.
- MOVIE_DATA_UPSTREAM_FAILED: provider connectivity or response error.

Secrets are never written by these log messages. Ordinary visitors see short availability messages, not .env instructions. Live search still requires valid credentials and upstream connectivity. No fake reviews or substitute sample catalogue are added.

## Checks

Run `python -m unittest discover -s tests -v` in the project's virtual environment. Tests use mocked upstream calls and do not verify your Render secrets or live TMDB connectivity.
