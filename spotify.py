# spotify.py
import requests
import base64
import re
import time

class SpotifyAPI:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token = self.refresh_access_token()
        self.search_cache = {}

    def refresh_access_token(self):
        token_url = 'https://accounts.spotify.com/api/token'
        headers = {
            'Authorization': 'Basic ' + base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode(),
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        response = requests.post(token_url, headers=headers, data=data)
        if not response.ok:
            raise RuntimeError(
                f'Spotify token refresh failed ({response.status_code}): {response.text}'
            )
        return response.json()['access_token']

    def fetch_web_api(self, endpoint, method='GET', body=None):
        url = f'https://api.spotify.com/v1/{endpoint}'
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        retries = 0
        while True:
            response = requests.request(method, url, json=body, headers=headers)
            if response.status_code == 401:
                print('Refreshing access token...')
                self.token = self.refresh_access_token()
                headers['Authorization'] = f'Bearer {self.token}'
                response = requests.request(method, url, json=body, headers=headers)
            if response.status_code in {429, 500, 502, 503, 504} and retries < 2:
                retry_after = None
                if 'Retry-After' in response.headers:
                    try:
                        retry_after = int(response.headers['Retry-After'])
                    except ValueError:
                        retry_after = None
                delay = min(max(retry_after if retry_after is not None else 2, 2), 8)
                print(f'Spotify transient error ({response.status_code}). Retrying in {delay}s...')
                time.sleep(delay)
                retries += 1
                continue
            if response.status_code == 429:
                print('Spotify rate limit exceeded. Skipping this request.')
                return None
            response.raise_for_status()
            if response.status_code == 200 and not response.content.strip():
                return None
            return response.json()

    def get_playlist_tracks(self, playlist_id):
        fields = 'items(track(id,uri,name,artists(name),album(release_date),popularity),added_at)'
        tracks = []
        offset = 0
        while True:
            endpoint = f'playlists/{playlist_id}/tracks?fields={fields}&limit=100&offset={offset}'
            try:
                data = self.fetch_web_api(endpoint)
            except requests.HTTPError as exc:
                if getattr(exc.response, 'status_code', None) == 403:
                    print('Warning: unable to read existing playlist tracks. Continuing with add-only sync.')
                    return []
                raise
            items = data.get('items', [])
            tracks += [
                {
                    'id': item['track']['id'],
                    'uri': item['track']['uri'],
                    'song_name': item['track']['name'],
                    'artists': ', '.join(artist.get('name', '') for artist in item['track'].get('artists', []) if artist.get('name')),
                    'date_added': item['added_at'],
                    'release_date': item['track'].get('album', {}).get('release_date', ''),
                    'popularity': item['track'].get('popularity')
                }
                for item in items if item.get('track')
            ]
            if len(items) < 100:
                break
            offset += 100
        return tracks

    def _make_track_result(self, track):
        album = track.get('album') or {}
        artists = track.get('artists') or []
        return {
            'id': track.get('id'),
            'uri': track.get('uri'),
            'song_name': track.get('name'),
            'artists': ', '.join(a.get('name', '') for a in artists if a.get('name')),
            'album': album.get('name', ''),
            'release_date': album.get('release_date', ''),
            'popularity': track.get('popularity'),
        }

    def search_song(self, query, limit=10):
        if query in self.search_cache:
            return self.search_cache[query]

        time.sleep(0.3)
        endpoint = f'search?q={query}&type=track&limit={limit}'
        data = self.fetch_web_api(endpoint)
        if not data:
            self.search_cache[query] = None
            return None
        tracks = data.get('tracks', {}).get('items', [])
        if not tracks:
            self.search_cache[query] = None
            return None

        # Pass 1: full query is a substring of track name or combined artists
        for track in tracks:
            track_artists = ', '.join(a['name'] for a in track['artists'])
            if query.lower() in track['name'].lower() or query.lower() in track_artists.lower():
                result = self._make_track_result(track)
                self.search_cache[query] = result
                return result

        stop_words = {'the', 'a', 'an', 'and', 'or', 'by', 'ft', 'feat', 'with', 'of', 'in', 'on'}
        query_words = {w.lower() for w in query.split() if len(w) > 2 and w.lower() not in stop_words}

        # Pass 2: artist-name matching
        for track in tracks:
            title_words = set(track['name'].lower().split())
            matched_artists = sum(
                1 for artist in track['artists']
                if query_words & {w.lower() for w in re.split(r'\W+', artist['name']) if len(w) > 2}
            )
            if matched_artists >= 2:
                result = self._make_track_result(track)
                self.search_cache[query] = result
                return result
            if matched_artists == 1:
                if query_words & title_words:
                    result = self._make_track_result(track)
                    self.search_cache[query] = result
                    return result
                if any(
                    len(qw) >= 4 and len(tw) >= 4 and (qw in tw or tw in qw)
                    for qw in query_words for tw in title_words
                ):
                    result = self._make_track_result(track)
                    self.search_cache[query] = result
                    return result

        # Pass 3: two or more query words appear in the track title
        for track in tracks:
            if len(query_words & set(track['name'].lower().split())) >= 2:
                result = self._make_track_result(track)
                self.search_cache[query] = result
                return result

        self.search_cache[query] = None
        return None

    def create_playlist(self, name, public=False):
        endpoint = 'me/playlists'
        response = self.fetch_web_api(endpoint, method='POST', body={'name': name, 'public': public})
        return response

    def add_tracks_to_playlist(self, playlist_id, track_uris):
        endpoint = f'playlists/{playlist_id}/tracks'
        batch_size = 100
        existing_uris = {track['uri'] for track in self.get_playlist_tracks(playlist_id)}
        unique_uris = [uri for uri in track_uris if uri not in existing_uris]
        total = len(unique_uris)

        for i in range(0, total, batch_size):
            batch = unique_uris[i:i + batch_size]
            try:
                response = self.fetch_web_api(endpoint, method='POST', body={'uris': batch})
            except requests.HTTPError as exc:
                if getattr(exc.response, 'status_code', None) == 403:
                    print('Warning: playlist add denied by Spotify for this playlist.')
                    return
                raise
            if response.get('snapshot_id'):
                print(f"Added {len(batch)} tracks - {i + len(batch)}/{total} complete.")
            else:
                print(f"Failed to add batch starting at {i}.")

        print(f"Finished adding all {total} tracks.")

    def remove_tracks_from_playlist(self, playlist_id, track_uris):
        endpoint = f'playlists/{playlist_id}/tracks'
        batch_size = 100
        try:
            for i in range(0, len(track_uris), batch_size):
                batch = [{'uri': uri} for uri in track_uris[i:i + batch_size]]
                self.fetch_web_api(endpoint, method='DELETE', body={'tracks': batch})
                print(f"Removed {len(batch)} tracks from playlist.")
        except requests.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) == 403:
                print('Warning: playlist remove denied by Spotify for this playlist.')
                return
            raise

    def reorder_playlist_tracks(self, playlist_id, track_uris):
        endpoint = f'playlists/{playlist_id}/tracks'
        try:
            body = {'uris': track_uris[:100]}
            self.fetch_web_api(endpoint, method='PUT', body=body)

            current_tracks = self.get_playlist_tracks(playlist_id)
            if not current_tracks:
                print('Skipping reorder because existing playlist tracks could not be read.')
                return
            current_uris = [t['uri'] for t in current_tracks]

            for i, uri in enumerate(track_uris):
                current_index = current_uris.index(uri)
                if current_index != i:
                    body = {'range_start': current_index, 'insert_before': i}
                    self.fetch_web_api(f'playlists/{playlist_id}/tracks', method='PUT', body=body)
                    current_uris.insert(i, current_uris.pop(current_index))

            print(f"Finished reordering {len(track_uris)} tracks.")
        except requests.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) == 403:
                print('Warning: playlist reorder denied by Spotify for this playlist.')
                return
            raise

    def reorder_playlist_many_tracks(self, playlist_id, track_uris):
        try:
            current_tracks = self.get_playlist_tracks(playlist_id)
            if not current_tracks:
                print('Skipping reorder because existing playlist tracks could not be read.')
                return
            current_uris = [t['uri'] for t in current_tracks]

            uri_set = set(current_uris)
            final_order = [uri for uri in track_uris if uri in uri_set]
            current_order = list(current_uris)

            for i, uri in enumerate(final_order):
                current_pos = current_order.index(uri)
                if current_pos != i:
                    self.fetch_web_api(
                        f'playlists/{playlist_id}/tracks',
                        method='PUT',
                        body={'range_start': current_pos, 'insert_before': i}
                    )
                    current_order.insert(i, current_order.pop(current_pos))

            print(f"Finished reordering {len(final_order)} tracks.")
        except requests.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) == 403:
                print('Warning: playlist reorder denied by Spotify for this playlist.')
                return
            raise