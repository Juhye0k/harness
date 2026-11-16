"""YouTube OAuth and resumable HTTP adapter. No implicit retries or redirects."""

import base64
import hashlib
import json
import re
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.domain.sns import SnsError

SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
)
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


class ProviderFailure(Exception):
    def __init__(self, code="PROVIDER_REJECTED", *, ambiguous=False):
        super().__init__(code)
        self.code, self.ambiguous = code, ambiguous


class TokenCipher:
    def __init__(self, settings):
        try:
            self.cipher = Fernet(settings.sns_token_key.get_secret_value().encode())
        except (ValueError, TypeError) as exc:
            raise SnsError("SNS_NOT_CONFIGURED", "SNS 암호화 설정을 확인하세요.", 503) from exc

    def encrypt(self, value):
        return self.cipher.encrypt(json.dumps(value).encode()).decode()

    def decrypt(self, value):
        try:
            return json.loads(self.cipher.decrypt(value.encode()))
        except (InvalidToken, ValueError, TypeError) as exc:
            raise ProviderFailure("CREDENTIALS_UNAVAILABLE") from exc


def authorization_url(settings, state, verifier):
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        dict(
            client_id=settings.youtube_client_id,
            redirect_uri=settings.sns_origin + "/sns/youtube/callback",
            response_type="code",
            scope=" ".join(SCOPES),
            access_type="offline",
            prompt="consent select_account",
            state=state,
            code_challenge=challenge.decode(),
            code_challenge_method="S256",
        )
    )


def session_url(uri):
    parsed = urlsplit(uri)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.googleapis.com"
        or parsed.path != "/upload/youtube/v3/videos"
        or not parsed.query
        or parsed.fragment
    ):
        raise ProviderFailure("INVALID_PROVIDER_RESPONSE", ambiguous=True)
    return uri


class YouTubeProvider:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def request(self, method, url, **kwargs):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(120, connect=10),
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                return client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            # Even a timeout can follow a successful remote write.
            raise ProviderFailure("PROVIDER_UNREACHABLE", ambiguous=True) from exc

    @staticmethod
    def payload(response, *, write=False):
        if response.status_code not in (200, 201):
            code = "RECONNECT_REQUIRED" if response.status_code == 401 else "PROVIDER_REJECTED"
            raise ProviderFailure(code, ambiguous=write and response.status_code >= 500)
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except ValueError as exc:
            raise ProviderFailure("INVALID_PROVIDER_RESPONSE", ambiguous=write) from exc

    def token(self, **values):
        response = self.request(
            "POST",
            TOKEN_URL,
            data={
                "client_id": self.settings.youtube_client_id,
                "client_secret": self.settings.youtube_client_secret.get_secret_value(),
                **values,
            },
        )
        data = self.payload(response)
        if not isinstance(data.get("access_token"), str) or not data["access_token"]:
            raise ProviderFailure("RECONNECT_REQUIRED")
        return data

    def exchange(self, code, verifier):
        tokens = self.token(
            code=code,
            code_verifier=verifier,
            grant_type="authorization_code",
            redirect_uri=self.settings.sns_origin + "/sns/youtube/callback",
        )
        if not tokens.get("refresh_token") or not set(SCOPES) <= set(
            tokens.get("scope", "").split()
        ):
            raise ProviderFailure("RECONNECT_REQUIRED")
        channel = self.channel(tokens["access_token"])
        return {"refresh_token": tokens["refresh_token"]}, channel

    def access_token(self, credentials):
        return self.token(refresh_token=credentials["refresh_token"], grant_type="refresh_token")[
            "access_token"
        ]

    def channel(self, access_token):
        response = self.request(
            "GET",
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        data = self.payload(response)
        items = data.get("items", [])
        if len(items) != 1 or not items[0].get("id"):
            raise ProviderFailure("CHANNEL_UNAVAILABLE")
        return {"id": items[0]["id"], "title": items[0].get("snippet", {}).get("title", "YouTube")}

    def initiate(self, token, upload, size):
        response = self.request(
            "POST",
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(size),
            },
            json={
                "snippet": {"title": upload.title, "categoryId": "22"},
                "status": {
                    "privacyStatus": upload.privacy,
                    "selfDeclaredMadeForKids": upload.made_for_kids,
                },
            },
        )
        if response.status_code != 200:
            self.payload(response, write=True)
            raise ProviderFailure("INVALID_PROVIDER_RESPONSE", ambiguous=True)
        return session_url(response.headers.get("Location", ""))

    def send(self, token, uri, stream, size):
        def chunks():
            while chunk := stream.read(1024 * 1024):
                yield chunk

        response = self.request(
            "PUT",
            session_url(uri),
            content=chunks(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
            },
        )
        if response.status_code == 308:
            raise ProviderFailure("UPLOAD_INCOMPLETE", ambiguous=True)
        return self.video(self.payload(response, write=True))

    @staticmethod
    def video(data):
        if not VIDEO_ID.fullmatch(str(data.get("id", ""))):
            raise ProviderFailure("INVALID_PROVIDER_RESPONSE", ambiguous=True)
        return data["id"]

    def probe(self, token, uri, size):
        response = self.request(
            "PUT",
            session_url(uri),
            content=b"",
            headers={"Authorization": f"Bearer {token}", "Content-Range": f"bytes */{size}"},
        )
        # This endpoint never re-sends media or initiates a new session.
        if response.status_code in (308, 404, 410):
            return None
        return self.video(self.payload(response, write=True))
