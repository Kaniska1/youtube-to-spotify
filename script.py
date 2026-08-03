from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from spotify import SpotifyAPI, SpotifyTrack
from youtube import YouTubeAPI, YouTubeVideo, clean_youtube_title, split_artist_title


REPORT_FILE = Path("sync_report.csv")
CACHE_FILE = Path("resolved_tracks.json")


@dataclass
class MatchResult:
    video: YouTubeVideo
    track: SpotifyTrack | None
    query: str


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def find_spotify_match(
    spotify: SpotifyAPI,
    video: YouTubeVideo,
    market: str,
    minimum_score: float,
) -> MatchResult:
    cleaned = clean_youtube_title(video.title)
    best: SpotifyTrack | None = None
    best_query = cleaned

    for artist, song in split_artist_title(video.title):
        result = spotify.search_track(
            song=song,
            artist=artist,
            fallback_query=cleaned,
            market=market,
            minimum_score=minimum_score,
        )

        if result and (best is None or result.score > best.score):
            best = result
            best_query = f"{artist} - {song}" if artist else song

    if best is None and video.channel_title:
        channel_artist = (
            video.channel_title
            .replace("VEVO", "")
            .replace("Official", "")
            .strip()
        )

        result = spotify.search_track(
            song=cleaned,
            artist=channel_artist,
            fallback_query=f"{cleaned} {channel_artist}",
            market=market,
            minimum_score=minimum_score,
        )

        if result:
            best = result
            best_query = f"{channel_artist} - {cleaned}"

    return MatchResult(video=video, track=best, query=best_query)


def write_report(
    results: list[MatchResult],
    path: Path = REPORT_FILE,
) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "youtube_title",
                "youtube_url",
                "search_query",
                "status",
                "spotify_track",
                "spotify_artist",
                "spotify_album",
                "confidence",
                "spotify_uri",
            ]
        )

        for result in results:
            track = result.track
            writer.writerow(
                [
                    result.video.title,
                    result.video.url,
                    result.query,
                    "matched" if track else "not_found",
                    track.name if track else "",
                    track.artists if track else "",
                    track.album if track else "",
                    f"{track.score:.3f}" if track else "",
                    track.uri if track else "",
                ]
            )


def save_resolved_tracks(
    results: list[MatchResult],
    youtube_playlist_id: str,
    path: Path = CACHE_FILE,
) -> None:
    matched_tracks: list[dict[str, object]] = []

    for result in results:
        if result.track is None:
            continue

        matched_tracks.append(
            {
                "youtube_title": result.video.title,
                "youtube_url": result.video.url,
                "search_query": result.query,
                "spotify_uri": result.track.uri,
                "spotify_track": result.track.name,
                "spotify_artists": result.track.artists,
                "spotify_album": result.track.album,
                "confidence": round(result.track.score, 4),
            }
        )

    payload = {
        "youtube_playlist_id": youtube_playlist_id,
        "matched_count": len(matched_tracks),
        "tracks": matched_tracks,
    }

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    print(f"  Cache: {path}")


def load_resolved_uris(
    expected_youtube_playlist_id: str,
    path: Path = CACHE_FILE,
) -> list[str]:
    if not path.exists():
        raise RuntimeError(
            f"{path} was not found. Run once with DRY_RUN=true first."
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} contains invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} has an invalid structure.")

    cached_playlist_id = str(payload.get("youtube_playlist_id", "")).strip()

    if cached_playlist_id and cached_playlist_id != expected_youtube_playlist_id:
        raise RuntimeError(
            "The cache belongs to a different YouTube playlist. "
            "Delete resolved_tracks.json and run again with DRY_RUN=true."
        )

    tracks = payload.get("tracks")
    if not isinstance(tracks, list):
        raise RuntimeError(f"{path} does not contain a valid tracks list.")

    uris: list[str] = []

    for item in tracks:
        if not isinstance(item, dict):
            continue

        uri = str(item.get("spotify_uri", "")).strip()
        if uri:
            uris.append(uri)

    if not uris:
        raise RuntimeError(f"{path} contains no Spotify track URIs.")

    return uris


def resolve_and_cache_tracks(
    spotify: SpotifyAPI,
    youtube: YouTubeAPI,
    youtube_playlist_id: str,
    market: str,
    minimum_score: float,
) -> int:
    print("Fetching the YouTube playlist...")
    videos = youtube.get_playlist_items(youtube_playlist_id)

    if not videos:
        raise RuntimeError(
            "No accessible videos were found in the YouTube playlist."
        )

    print(f"Found {len(videos)} accessible YouTube videos.\n")

    results: list[MatchResult] = []

    for index, video in enumerate(videos, start=1):
        result = find_spotify_match(
            spotify=spotify,
            video=video,
            market=market,
            minimum_score=minimum_score,
        )
        results.append(result)

        if result.track:
            print(
                f"[{index}/{len(videos)}] MATCH {result.track.score:.2f}: "
                f"{video.title} -> "
                f"{result.track.name} — {result.track.artists}"
            )
        else:
            print(f"[{index}/{len(videos)}] NOT FOUND: {video.title}")

    write_report(results)
    save_resolved_tracks(
        results=results,
        youtube_playlist_id=youtube_playlist_id,
    )

    matched = sum(1 for result in results if result.track is not None)
    unmatched = len(videos) - matched

    print("\nMatch summary")
    print(f"  YouTube videos: {len(videos)}")
    print(f"  Spotify matches: {matched}")
    print(f"  Not matched: {unmatched}")
    print(f"  Report: {REPORT_FILE}")

    if matched == 0:
        raise RuntimeError(
            "No tracks matched; Spotify playlist was left unchanged."
        )

    print("\nDRY_RUN=true, so the Spotify playlist was not modified.")
    print(
        "The successful matches were saved to resolved_tracks.json. "
        "Set DRY_RUN=false to reuse them without searching Spotify again."
    )

    return 0


def sync_cached_tracks(
    spotify: SpotifyAPI,
    spotify_playlist_id: str,
    youtube_playlist_id: str,
) -> int:
    print("Loading previously resolved Spotify tracks...")
    matched_uris = load_resolved_uris(youtube_playlist_id)

    print(f"Loaded {len(matched_uris)} cached Spotify tracks.")
    print("No Spotify search requests will be made.")
    print(
        "Replacing the Spotify playlist with the cached tracks "
        "in YouTube order..."
    )

    spotify.replace_playlist_items(
        spotify_playlist_id,
        matched_uris,
    )

    print(
        f"Done. Spotify playlist now contains "
        f"{len(matched_uris)} matched tracks in order."
    )

    return 0


def main() -> int:
    load_dotenv()

    client_id = require_env("CLIENT_ID")
    client_secret = require_env("CLIENT_SECRET")
    refresh_token = require_env("REFRESH_TOKEN")
    spotify_playlist_id = require_env("SPOTIFY_PLAYLIST_ID")
    youtube_api_key = require_env("API_KEY")
    youtube_playlist_id = require_env("YOUTUBE_PLAYLIST_ID")

    market = os.getenv("SPOTIFY_MARKET", "IN").strip() or "IN"
    minimum_score = float(os.getenv("MINIMUM_MATCH_SCORE", "0.70"))
    dry_run = parse_bool(os.getenv("DRY_RUN", "false"))

    spotify = SpotifyAPI(
        client_id,
        client_secret,
        refresh_token,
    )

    spotify.verify_playlist_access(spotify_playlist_id)

    if dry_run:
        youtube = YouTubeAPI(youtube_api_key)
        return resolve_and_cache_tracks(
            spotify=spotify,
            youtube=youtube,
            youtube_playlist_id=youtube_playlist_id,
            market=market,
            minimum_score=minimum_score,
        )

    return sync_cached_tracks(
        spotify=spotify,
        spotify_playlist_id=spotify_playlist_id,
        youtube_playlist_id=youtube_playlist_id,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except (RuntimeError, ValueError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)