# youtube-to-spotify

Sync a YouTube playlist to a Spotify playlist: the script scans a YouTube playlist, attempts to match each video title to a Spotify track, adds missing tracks, removes tracks that no longer appear on the YouTube playlist (optional), and reorders the Spotify playlist to mirror the YouTube order.

## Features
- Fetches all videos from a YouTube playlist (handles pagination).
- Attempts robust matching between YouTube titles and Spotify tracks (noise removal, bracket alternatives).
- Adds missing tracks to a Spotify playlist and optionally removes obsolete ones.
- Reorders the Spotify playlist to match YouTube ordering. Uses a batching strategy for large playlists.

## Stack
- Language: Python 3.8+
- Libraries (key): google-api-python-client, google-auth, requests, python-dotenv

## Repository layout
```
README.md                 # (this file)
requirements.txt          # Python dependencies
script.py                 # CLI entry point: orchestrates sync flow
youtube.py                # YouTube helper: fetches playlist items and cleans titles
spotify.py                # Spotify helper: token management, search, add/remove/reorder
get_refresh_token.py      # One-off helper to obtain a Spotify refresh token via auth flow
.github/                  # CI/workflows (if present)
```

## Requirements
- Python 3.8 or newer
- A Spotify Developer app (Client ID + Client Secret)
- A Spotify refresh token for the account that will modify playlists
- A Spotify playlist ID you want to sync to
- A Google API key with access to the YouTube Data API v3
- The Python dependencies listed in requirements.txt

requirements.txt contains:
- google-api-python-client
- google-auth
- google-auth-httplib2
- python-dotenv
- requests

Install them:
```bash
pip install -r requirements.txt
```

## Environment variables
Create a `.env` file in the repository root containing these values:

- CLIENT_ID — Spotify app client ID
- CLIENT_SECRET — Spotify app client secret
- REFRESH_TOKEN — Spotify refresh token for the user account (see below)
- SPOTIFY_PLAYLIST_ID — Spotify playlist to sync (playlist ID)
- API_KEY — Google API key (YouTube Data API v3)
- YOUTUBE_PLAYLIST_ID — YouTube playlist ID to mirror

Example `.env`:
```env
CLIENT_ID=your_spotify_client_id
CLIENT_SECRET=your_spotify_client_secret
REFRESH_TOKEN=your_spotify_refresh_token
SPOTIFY_PLAYLIST_ID=37i9dQZF1DX...
API_KEY=AIza...
YOUTUBE_PLAYLIST_ID=PLxxxxxxxxxxxxxxxx
```

## Obtaining a Spotify refresh token
A helper script `get_refresh_token.py` is included to perform the Authorization Code flow in a local browser and print a refresh token. Before running it:

1. In your Spotify Developer Dashboard, add this Redirect URI to your app:
   - http://127.0.0.1:8888/callback

2. Create a `.env` with CLIENT_ID and CLIENT_SECRET (the helper will read them).
3. Run:
```bash
python get_refresh_token.py
```
The script opens a browser; after approving, it prints the refresh token. Copy that value into REFRESH_TOKEN in your `.env`.

## How to run (detailed)
These steps assume you cloned the repo and are in its root directory.

1) Create and activate a virtual environment

- Unix / macOS (bash/zsh):
```bash
python -m venv venv
source venv/bin/activate
```

- Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

- Windows (cmd.exe):
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Create the `.env` file

Create a file named `.env` in the project root (same directory as `script.py`) and add the environment variables shown above. Example:

```env
CLIENT_ID=your_spotify_client_id
CLIENT_SECRET=your_spotify_client_secret
REFRESH_TOKEN=your_spotify_refresh_token
SPOTIFY_PLAYLIST_ID=37i9dQZF1DX...
API_KEY=AIza...
YOUTUBE_PLAYLIST_ID=PLxxxxxxxxxxxxxxxx
```

If you do not yet have a REFRESH_TOKEN, follow the "Obtaining a Spotify refresh token" section above.

4) Run the sync script

```bash
python script.py
```

What the script does:
- Loads credentials from `.env`.
- Fetches the YouTube playlist items.
- Uses heuristics to match each video title to a Spotify track.
- Adds missing tracks to the Spotify playlist, optionally removes tracks that no longer appear on YouTube, and reorders the playlist to match the YouTube order.

5) (Optional) Run as a module / call programmatically

You can also import and call the sync function from another Python script or REPL:

```python
from script import sync_playlist, SpotifyAPI, YouTubeAPI

# initialize APIs
spotify = SpotifyAPI(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
youtube = YouTubeAPI(API_KEY)

sync_playlist(SPOTIFY_PLAYLIST_ID, YOUTUBE_PLAYLIST_ID, spotify, youtube, remove=True)
```

## Notes, limits, and behavior
- YouTube API quotas apply (use an API key tied to a project with YouTube Data API enabled).
- Spotify rate limits apply; the script includes batching for add/remove operations but may still be throttled for very large playlists.
- Spotify's reorder and add endpoints have constraints (100 URIs per request for some endpoints); the implementation batches accordingly.
- Titles that are "Deleted" or "Private" are skipped.
- Matching is heuristic and not perfect — some videos may not be matched to the intended track (artist/title variations, covers, etc.). The script prints which items were not found.

## Troubleshooting
- Token refresh failures: ensure CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN are correct and the refresh token hasn't been revoked.
- 401 errors from Spotify: the script attempts to refresh the access token automatically. If that repeatedly fails, re-run the refresh token flow.
- YouTube quota errors: check API key and quota usage in Google Cloud Console.
- Encoding / title parsing issues: some titles contain non-standard punctuation or language-specific characters — consider pre-cleaning titles if you see many mismatches.

## Development & Contribution
- The code is simple, single-module helpers for YouTube and Spotify. Follow common Python packaging/contribution practices if you want to add tests or CI.
- To add improvements:
  - Improve matching heuristics in spotify.search_song or youtube.clean_title.
  - Add a dry-run mode to preview changes before they are applied.
  - Add logging and configurable verbosity.

## Example workflow
1. Clone repo
2. Create `.env` with CLIENT_ID and CLIENT_SECRET
3. Run `python get_refresh_token.py` to obtain REFRESH_TOKEN
4. Fill remaining variables in `.env` (SPOTIFY_PLAYLIST_ID, API_KEY, YOUTUBE_PLAYLIST_ID)
5. Install deps and run:
```bash
pip install -r requirements.txt
python script.py
```

## License
Choose and add a license if you intend to publish this publicly (e.g., MIT).

## Acknowledgements
- Uses Google API Python client for YouTube Data API v3
- Uses Spotify Web API
