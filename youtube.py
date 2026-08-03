from __future__ import annotations

import re
from dataclasses import dataclass

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError



@dataclass(frozen=True)
class YouTubeVideo:
    title: str
    video_id: str
    channel_title: str

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class YouTubeAPI:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("YouTube API key is required.")
        self.youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def get_playlist_items(self, playlist_id: str) -> list[YouTubeVideo]:
        """Return every accessible video in playlist order."""
        videos: list[YouTubeVideo] = []
        page_token: str | None = None

        try:
            while True:
                response = self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=page_token,
                ).execute()

                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    title = (snippet.get("title") or "").strip()
                    video_id = (
                        snippet.get("resourceId", {}).get("videoId")
                        or snippet.get("videoOwnerChannelId")
                        or ""
                    )
                    channel_title = (snippet.get("videoOwnerChannelTitle") or "").strip()

                    if not title or not video_id:
                        continue
                    if title.lower() in {"deleted video", "private video"}:
                        continue

                    videos.append(
                        YouTubeVideo(
                            title=title,
                            video_id=video_id,
                            channel_title=channel_title,
                        )
                    )

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            raise RuntimeError(f"YouTube API request failed: {exc}") from exc

        return videos


_NOISE = re.compile(
    r"\b(?:official(?:\s+music)?\s+video|official\s+audio|lyrics?|lyric\s+video|"
    r"visuali[sz]er|audio|music\s+video|video|hd|hq|4k|1080p|remastered?|"
    r"live(?:\s+performance|\s+session)?|cover|karaoke|sped\s+up|slowed(?:\s+and\s+reverb)?|"
    r"nightcore|radio\s+edit|extended(?:\s+mix)?|from\s+[^\]\)]+)\b",
    re.IGNORECASE,
)


def clean_youtube_title(title: str) -> str:
    """Remove common YouTube decoration while retaining useful remix/version text."""
    text = title.replace("–", "-").replace("—", "-").replace("｜", "|")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"#\w+", " ", text)

    def clean_bracket(match: re.Match[str]) -> str:
        inner = match.group(1)
        return " " if _NOISE.search(inner) else f" {inner} "

    text = re.sub(r"[\[(]([^\])]+)[\])]", clean_bracket, text)
    text = _NOISE.sub(" ", text)
    text = re.sub(r"\s*\|\s*.*$", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -_|:.")
    return text


def split_artist_title(title: str) -> list[tuple[str, str]]:
    """Return plausible (artist, song) pairs without pretending the title format is certain."""
    cleaned = clean_youtube_title(title)
    candidates: list[tuple[str, str]] = []

    for separator in (" - ", " – ", " — ", ": "):
        if separator in cleaned:
            left, right = cleaned.split(separator, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                candidates.extend([(left, right), (right, left)])
            break

    if not candidates:
        candidates.append(("", cleaned))

    # Preserve order and remove duplicates.
    return list(dict.fromkeys(candidates))