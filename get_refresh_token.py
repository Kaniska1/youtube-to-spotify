from __future__ import annotations

import base64
import hashlib
import os
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import load_dotenv, set_key

load_dotenv()

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"
CALLBACK: dict[str, str | None] = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        CALLBACK["code"] = params.get("code", [None])[0]
        CALLBACK["state"] = params.get("state", [None])[0]
        CALLBACK["error"] = params.get("error", [None])[0]

        success = bool(CALLBACK.get("code"))
        message = (
            "Spotify authorization completed. You may close this tab."
            if success
            else f"Authorization failed: {CALLBACK.get('error') or 'unknown error'}"
        )
        body = f"<html><body><h2>{message}</h2></body></html>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


def main() -> None:
    client_id = os.getenv("CLIENT_ID", "").strip()
    client_secret = os.getenv("CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit("Add CLIENT_ID and CLIENT_SECRET to .env first.")

    state = secrets.token_urlsafe(32)
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "show_dialog": "true",
        }
    )

    print("Opening Spotify authorization in your browser...")
    print(auth_url)
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    server.timeout = 180
    server.handle_request()
    server.server_close()

    if CALLBACK.get("error"):
        raise SystemExit(f"Spotify authorization failed: {CALLBACK['error']}")
    if not CALLBACK.get("code"):
        raise SystemExit("No callback received within 3 minutes.")
    if CALLBACK.get("state") != state:
        raise SystemExit("OAuth state mismatch. Authorization was rejected for safety.")

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": CALLBACK["code"],
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    if not response.ok:
        raise SystemExit(f"Token exchange failed ({response.status_code}): {response.text}")

    payload = response.json()
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise SystemExit("Spotify did not return a refresh token. Revoke app access and retry.")

    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        open(env_path, "a", encoding="utf-8").close()
    set_key(env_path, "REFRESH_TOKEN", refresh_token, quote_mode="never")

    print("\nRefresh token generated and saved to .env as REFRESH_TOKEN.")
    print(f"Granted scopes: {payload.get('scope', '')}")


if __name__ == "__main__":
    main()