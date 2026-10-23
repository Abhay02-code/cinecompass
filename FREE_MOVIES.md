# Free movie discovery & watch links — CineCompass 3.4.0

## What is included

- Public /free-movies catalogue, linked in the navigation.
- India selected by default; country choices IN/US/GB/CA/AU. No IP geolocation is used.
- Free without ads / Free with ads / All free offers filters and live catalogue pagination.
- Movie detail pages show the free providers reported for the selected country. Subscription, rent, purchase and trials are not labelled free.
- An owner-only link editor at /admin/watch-links can publish exact official full-movie links after your own source/access check. Those links open directly on the external platform, in a new tab.
- Original TMDB reviews, CineCompass ratings/reviews, accounts, watchlist, creator credit and analytics remain available.

No new API key is needed for the basic catalogue: your existing TMDB Read Access Token supplies discovery/provider listings. No streaming player, video files, downloads or access bypasses are added.

## Important: automatic listing is not an automatic direct link

TMDB's watch-provider endpoint explicitly does NOT return full provider deep links. It reports provider names/offer categories per country and a TMDB movie watch-page URL. Source: https://developer.themoviedb.org/reference/movie-watch-providers

Accordingly:

| Button | Actual destination |
| --- | --- |
| Check free options on TMDB | The provider-supplied TMDB movie watch-options page, where the visitor can choose a provider. That page can also show paid offers. |
| Watch free / Watch free on [platform] | An exact external movie-page URL checked and published by you in the owner editor. |

A platform homepage, search results page or YouTube search is not presented as an exact movie link. There are no fabricated provider URLs, sample movies or pre-approved free videos bundled in this patch. If you have not added exact links, the catalogue and reported providers work, but direct Watch free buttons will not appear.

To automate provider deep links at scale you would need an authorised data source/partner feed supplying those URLs, such as a suitable JustWatch partner integration. It is NOT secretly scraped or included here. See https://apis.justwatch.com/docs/content_partner/ . This update does not imply a commercial data licence or guarantee availability.

## 1. Apply to your EXISTING project

Extract the ZIP to Downloads/cinecompass-free-movies-v7. Open the existing GitHub-connected project in VS Code (not the patch's files folder).

Your earlier project path was:

```text
C:\Users\BITPATNA\Downloads\cinecompass-complete\cinecompass
```

Confirm the correct repository with `git remote -v`: it should point to Abhay02-code/cinecompass. From THAT folder's terminal:

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\cinecompass-free-movies-v7\apply_update.py"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe init_db.py
git add .
git commit -m "Add free movie discovery and owner-checked watch links"
git push
```

The updater backs up overwritten code in .cinecompass-backup and preserves .env, .git, trained models and existing database files. init_db.py adds the NEW free_watch_link table without resetting existing accounts, reviews or analytics. All previous code updates are included. No schema changes to existing tables are needed.

WTForms is pinned to the tested 3.3.0 release to keep forms consistent across deployments.

## 2. Deploy on Render

Keep your working environment variables exactly as configured:

- DATABASE_URL: your existing PostgreSQL connection URL.
- APP_ENV=production.
- SECRET_KEY: your existing fixed secret; do NOT regenerate it for this update.
- TMDB_READ_TOKEN: your existing valid Read Access Token.
- ADMIN_USER_ID: the ID of YOUR existing live account (previously confirmed as 1).
- PYTHON_VERSION=3.11.11.

Keep the current Start Command:

```bash
python init_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

On cinecompass-2 select Manual Deploy → Deploy latest commit if automatic deployment does not start. Check the NEW commit message, not a redeploy of an older commit. Wait for Live and `Database tables ready.`

Open https://cinecompass-2.onrender.com/api/status: version should be 3.4.0 and shared_account_database true. Then open https://cinecompass-2.onrender.com/free-movies . Hard-refresh the page if needed.

## 3. Publish an exact official movie link

1. Sign in as your configured owner account.
2. Open the movie you want to link and choose its viewing country.
3. In Free viewing options, click Manage links for this movie. Its movie ID and country are prefilled.
4. Independently open the actual full-movie page on the official service or an authorised uploader's channel.
5. Check that the title matches, it plays legally in that country, and no subscription, rental, purchase or time-limited trial is needed. A free account/ads may still be required; label the offer accurately.
6. Copy the exact movie URL, enter the real platform/authorised channel name, select the free offer type and tick the confirmation.
7. Publish. The movie page and the owner-checked shelf on Free movies will now have a direct Watch free button.

Only owner accounts can publish/manage these links. Ordinary visitors cannot submit outbound URLs. HTTPS/public URL checks block local addresses, credentials in URLs, homepages and common login/search endpoints. This syntactic check does NOT establish rights, prove the URL is the right movie, or verify that a provider remains free. You are responsible for checking the actual platform/channel and access conditions. The server never requests the submitted provider URL.

## 4. Keep links current

Owner links last 7 UTC calendar days including the checked day. After the displayed expiry date they are automatically hidden from public pages; the records remain in the owner editor. Recheck the title, region, authorised source and free access, then tick the confirmation and Renew. Remove links that become paid, unavailable or unauthorised. Republishing the same movie/country/URL updates one record instead of duplicating it.

The owner editor displays the most recent 100 stored links; the free catalogue's direct-link shelf shows up to 40 current offers. The automatic TMDB catalogue has separate pagination. Exact-link curation and automatic provider listings are separate sources, clearly described in the UI.

## Availability and attribution

TMDB discovery uses `watch_region` and `with_watch_monetization_types=free|ads` (or one selected free type); flatrate/rent/buy are not requested. Provider details display only the returned `free` and `ads` categories for that country. Absence of an offer means no free offer was reported, not proof that no legal free source exists. Upstream errors are labelled unavailable rather than "no free offers".

Source: https://developer.themoviedb.org/reference/discover-movie . Provider responses are cached by the existing TMDB fetch layer for up to 10 minutes; the upstream source itself can lag. Viewers should confirm current terms on the provider page.

JustWatch attribution is displayed on the catalogue, viewing section and footer, as required for TMDB watch-provider data. This does not make CineCompass endorsed by JustWatch or TMDB. The existing TMDB commercial-use conditions still apply; this feature does not grant a revenue-generating licence.

External sites have their own privacy/access terms. CineCompass does not send account passwords or review text to them. Anonymous analytics counts opted-in free-catalogue page views under a fixed path and does not record selected countries or outbound provider URLs.

## Verification

85 automated tests passed locally. Tests cover free-only discovery parameters, region/mode/pagination validation, paid-provider exclusions, no fabricated playback links, provider-versus-direct labels, safe link syntax, owner/CSRF protection, duplicate publishing, expiry, renewal/removal, empty/error states, additive database setup and existing features.

Browser checks passed for catalogue filters, country switching, owner link publishing, direct external navigation, removing links, mobile layouts, existing public reviews/sentiment/analytics and admin protection. TMDB responses and the external provider destination were mocked. No real streaming service, licence, commercial API access, playback, or your actual Render database was validated by these local tests.
