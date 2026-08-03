# YouTube to Spotify Playlist Sync

A Python-based playlist synchronization tool that transfers songs from a YouTube playlist to a Spotify playlist while preserving order and minimizing Spotify API usage.

## Features

- Fetches tracks from a YouTube playlist
- Intelligent Spotify track matching
- Confidence-based scoring for match quality
- CSV report generation (`sync_report.csv`)
- Cached Spotify URIs (`resolved_tracks.json`)
- Reuses cache to reduce Spotify API usage
- Preserves playlist order
- Handles Spotify OAuth and rate limits
- Supports dry-run mode for safe previews

## Tech Stack

- Python
- Spotify Web API
- YouTube Data API v3
- Requests
- python-dotenv

## Installation

```bash
git clone https://github.com/Kaniska1/youtube-to-spotify.git
cd youtube-to-spotify
python -m venv venv
```

### Activate Virtual Environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (cmd):**
```cmd
venv\Scripts\activate.bat
```

**macOS / Linux (bash/zsh):**
```bash
source venv/bin/activate
```

Then install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```env
CLIENT_ID=
CLIENT_SECRET=
REFRESH_TOKEN=
API_KEY=
YOUTUBE_PLAYLIST_ID=
SPOTIFY_PLAYLIST_ID=
SPOTIFY_MARKET=IN
MINIMUM_MATCH_SCORE=0.70
DRY_RUN=true
```

### Environment Variables

- `CLIENT_ID` - Spotify app client ID
- `CLIENT_SECRET` - Spotify app client secret
- `REFRESH_TOKEN` - Spotify refresh token
- `API_KEY` - YouTube Data API v3 key
- `YOUTUBE_PLAYLIST_ID` - Source YouTube playlist ID
- `SPOTIFY_PLAYLIST_ID` - Target Spotify playlist ID
- `SPOTIFY_MARKET` - Spotify market code (e.g., `IN`, `US`)
- `MINIMUM_MATCH_SCORE` - Match confidence threshold (e.g., `0.70`)
- `DRY_RUN` - `true` for preview mode, `false` for actual sync

## Usage

### Dry Run (Recommended First)

Set:

```env
DRY_RUN=true
```

Run:

```bash
python script.py
```

Generates:

- `sync_report.csv`
- `resolved_tracks.json`

No playlist changes are applied in dry run mode.

### Real Sync

Set:

```env
DRY_RUN=false
```

Run:

```bash
python script.py
```

The script reuses cached URIs from `resolved_tracks.json` to avoid searching Spotify again where possible, reducing API calls and improving performance.

## Output Files

- `sync_report.csv` - Detailed sync results and match decisions
- `resolved_tracks.json` - Cache of resolved YouTube-to-Spotify mappings

## Notes

- Run dry mode first to verify matches before updating playlists.
- If matching quality is too strict or too loose, tune `MINIMUM_MATCH_SCORE`.
- Keep your `.env` private and never commit secrets to GitHub.

## License

Add a license (e.g., MIT) if you plan to publish or distribute this project publicly.
