For signup/login fixes on an existing project, read AUTH_FIX.md.

Version 3.1.0. For an existing Render deployment, follow RENDER_FIX.md.

# Abhay — start here

## 1. Run in VS Code

Extract the ZIP. Open the `cinecompass` folder (the one with `app.py`) in VS Code.
Open Terminal → New Terminal:

```powershell
.\start.bat
```

Python 3.10–3.13 must be installed. This launcher uses your existing Python 3 instead of assuming Python 3.11 is present. If Python is missing, install Python 3.11 from python.org and reopen VS Code.

Open http://127.0.0.1:5000.

## 2. Live movies ke liye token add karo

Create a TMDB account → Settings → API → API Read Access Token.
Edit `.env` in this project folder:

```dotenv
TMDB_READ_TOKEN=your_read_access_token_here
```

Save, stop the running server with Ctrl+C, then run `start.bat` again.
This token is mandatory for live movies; it is not included in the ZIP.
Do not share the token or push `.env` to GitHub.

## 3. Try the full workflow

- Type at least two letters of a movie name. Suggestions appear below the search box.
- Click the correct movie/year to open audience reviews and sentiment. Arrow keys + Enter also work.
- View actual available English reviews and calculated sentiment.
- Create an account, save movies, like a few and choose genres in My library.
- Open For you for personalised recommendations.
- Paste your own English review. Tick Save to my history only if you want to store it.
- Open The model to inspect measured results and limitations.

There is no five-movie demo limit. Live catalogue coverage and review availability depend on TMDB.

## 4. GitHub + Render

Follow **README.md → Push to GitHub**, then **Deploy on Render**.
Render Blueprint creates a web service plus PostgreSQL. Add your token, review plans, then deploy. Secrets and database settings are supplied in Render, not by uploading `.env`.

The included trained sentiment model runs immediately after dependencies are installed; you do not need to retrain it.

## Updating from the previous ZIP

Extract this updated project into a separate folder. Copy your existing `.env` into its `cinecompass` folder, or enter the token again. Run `start.bat`. Do not replace your old `instance` folder if you want to retain the old local account data: after stopping both apps, you can copy the old `instance/cinecompass.db` into the new project’s `instance` folder. PostgreSQL data stays in the same configured database on Render; no schema change is required by this UI update.
