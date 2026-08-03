from __future__ import annotations

import base64
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class SpotifyTrack:
    uri: str
    name: str
    artists: str
    album: str
    score: float


class SpotifyAPI:
    API_BASE = "https://api.spotify.com/v1"
    TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        if not all((client_id, client_secret, refresh_token)):
            raise ValueError(
                "Spotify client ID, client secret, and refresh token are required."
            )

        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

        self.session = requests.Session()
        self.access_token = self.refresh_access_token()

        # Prevent duplicate Spotify searches during one execution.
        self._search_cache: dict[str, SpotifyTrack | None] = {}

    def refresh_access_token(self) -> str:
        credentials = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        encoded_credentials = base64.b64encode(credentials).decode("ascii")

        response = self.session.post(
            self.TOKEN_URL,
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            timeout=30,
        )

        if not response.ok:
            detail = response.text

            if response.status_code == 400 and "invalid_grant" in detail:
                raise RuntimeError(
                    "Spotify rejected REFRESH_TOKEN. Generate a new refresh token "
                    "using get_refresh_token.py with the same CLIENT_ID and CLIENT_SECRET."
                )

            raise RuntimeError(
                f"Spotify token refresh failed ({response.status_code}): {detail}"
            )

        payload = response.json()
        access_token = payload.get("access_token")

        if not access_token:
            raise RuntimeError(
                "Spotify token response did not contain an access token."
            )

        return access_token

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any] | None:
        url = f"{self.API_BASE}/{endpoint.lstrip('/')}"

        for attempt in range(retries + 1):
            response = self.session.request(
                method,
                url,
                params=params,
                json=json,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                },
                timeout=30,
            )

            if response.status_code == 401 and attempt == 0:
                self.access_token = self.refresh_access_token()
                continue

            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After", "5")

                try:
                    retry_after = int(retry_after_raw)
                except (TypeError, ValueError):
                    retry_after = 5

                try:
                    error_body = response.json()
                except ValueError:
                    error_body = {"raw": response.text}

                error_data = error_body.get("error", {})
                reason = error_data.get("reason", "RATE_LIMITED")
                message = error_data.get("message", "Too many requests")

                print("\nSpotify returned HTTP 429.")
                print(f"Reason: {reason}")
                print(f"Message: {message}")
                print(f"Retry-After: {retry_after} seconds")

                if retry_after > 300:
                    raise RuntimeError(
                        "Spotify quota has been exhausted. "
                        f"Spotify requested a retry after {retry_after} seconds. "
                        "Stop the program and try again after the quota resets."
                    )

                if attempt >= retries:
                    raise RuntimeError(
                        "Spotify rate limiting continued after all retry attempts."
                    )

                time.sleep(max(retry_after, 1))
                continue

            if 500 <= response.status_code < 600:
                if attempt >= retries:
                    raise RuntimeError(
                        f"Spotify server error after {retries + 1} attempts: "
                        f"{response.status_code} {response.text}"
                    )

                time.sleep(min(2**attempt, 20))
                continue

            if not response.ok:
                raise RuntimeError(
                    f"Spotify API {method} {endpoint} failed "
                    f"({response.status_code}): {response.text}"
                )

            if response.status_code == 204 or not response.content:
                return None

            return response.json()

        raise RuntimeError("Spotify request failed after all retries.")

    @staticmethod
    def _normalise(value: str) -> str:
        value = unicodedata.normalize("NFKD", value)
        value = value.encode("ascii", "ignore").decode("ascii")
        value = value.lower().replace("&", " and ")

        noise = (
            "feat.",
            "ft.",
            "featuring",
            "official music video",
            "official video",
            "official audio",
            "lyric video",
            "lyrics",
            "music video",
            "remastered",
            "hd",
            "hq",
        )

        for term in noise:
            value = value.replace(term, " ")

        value = "".join(
            character if character.isalnum() else " "
            for character in value
        )

        return " ".join(value.split())

    @classmethod
    def _similarity(cls, expected: str, actual: str) -> float:
        expected_normalised = cls._normalise(expected)
        actual_normalised = cls._normalise(actual)

        if not expected_normalised or not actual_normalised:
            return 0.0

        sequence_score = SequenceMatcher(
            None,
            expected_normalised,
            actual_normalised,
        ).ratio()

        expected_words = set(expected_normalised.split())
        actual_words = set(actual_normalised.split())

        union = expected_words | actual_words
        token_score = (
            len(expected_words & actual_words) / len(union)
            if union
            else 0.0
        )

        containment_score = 0.92 if (
            expected_normalised in actual_normalised
            or actual_normalised in expected_normalised
        ) else 0.0

        return max(sequence_score, token_score, containment_score)

    def _search_once(
        self,
        *,
        query: str,
        expected_song: str,
        expected_artist: str,
        market: str,
    ) -> SpotifyTrack | None:
        data = self._request(
            "GET",
            "search",
            params={
                "q": query,
                "type": "track",
                "limit": 10,
                "market": market,
            },
        ) or {}

        best: SpotifyTrack | None = None

        for item in data.get("tracks", {}).get("items", []):
            uri = item.get("uri")
            name = item.get("name", "")

            if not uri or not name:
                continue

            artists = ", ".join(
                artist.get("name", "")
                for artist in item.get("artists", [])
                if artist.get("name")
            )

            title_score = self._similarity(expected_song, name)
            artist_score = (
                self._similarity(expected_artist, artists)
                if expected_artist
                else 0.65
            )

            score = (0.72 * title_score) + (0.28 * artist_score)

            candidate = SpotifyTrack(
                uri=uri,
                name=name,
                artists=artists,
                album=item.get("album", {}).get("name", ""),
                score=score,
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def search_track(
        self,
        *,
        song: str,
        artist: str = "",
        fallback_query: str = "",
        market: str = "IN",
        minimum_score: float = 0.70,
    ) -> SpotifyTrack | None:
        song = song.strip()
        artist = artist.strip()
        fallback_query = fallback_query.strip()
        market = market.strip().upper() or "IN"

        cache_key = "|".join(
            (
                self._normalise(song),
                self._normalise(artist),
                self._normalise(fallback_query),
                market,
                f"{minimum_score:.3f}",
            )
        )

        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        queries: list[str] = []

        if song and artist:
            queries.append(f'track:"{song}" artist:"{artist}"')
        elif song:
            queries.append(song)
        elif fallback_query:
            queries.append(fallback_query)

        broad_query = " ".join(
            part for part in (song, artist) if part
        ).strip() or fallback_query

        if (
            broad_query
            and all(broad_query.lower() != query.lower() for query in queries)
        ):
            queries.append(broad_query)

        # Never use more than two Spotify searches for one song.
        queries = queries[:2]

        best: SpotifyTrack | None = None

        for index, query in enumerate(queries):
            candidate = self._search_once(
                query=query,
                expected_song=song or fallback_query,
                expected_artist=artist,
                market=market,
            )

            if candidate and (
                best is None or candidate.score > best.score
            ):
                best = candidate

            # Strong match: avoid an unnecessary second request.
            if best and best.score >= 0.90:
                break

            if index < len(queries) - 1:
                time.sleep(0.15)

        result = (
            best
            if best and best.score >= minimum_score
            else None
        )

        self._search_cache[cache_key] = result
        return result

    def verify_playlist_access(self, playlist_id: str) -> None:
        playlist_id = playlist_id.strip()

        if not playlist_id:
            raise ValueError("Spotify playlist ID is required.")

        self._request(
            "GET",
            f"playlists/{quote(playlist_id, safe='')}",
        )

    def replace_playlist_items(
        self,
        playlist_id: str,
        uris: list[str],
    ) -> None:
        playlist_id = playlist_id.strip()

        if not playlist_id:
            raise ValueError("Spotify playlist ID is required.")

        if not uris:
            raise ValueError(
                "No Spotify track URIs were supplied. "
                "The playlist was not modified."
            )

        endpoint = f"playlists/{quote(playlist_id, safe='')}/items"

        first_batch = uris[:100]

        self._request(
            "PUT",
            endpoint,
            json={"uris": first_batch},
        )

        print(f"Uploaded {len(first_batch)}/{len(uris)} Spotify tracks...")

        for start in range(100, len(uris), 100):
            batch = uris[start:start + 100]

            self._request(
                "POST",
                endpoint,
                json={"uris": batch},
            )

            uploaded = min(start + len(batch), len(uris))
            print(f"Uploaded {uploaded}/{len(uris)} Spotify tracks...")