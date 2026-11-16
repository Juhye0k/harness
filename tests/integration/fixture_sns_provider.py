"""Integration-only provider; no external HTTP, real credentials or real videos sent."""

from urllib.parse import parse_qs, urlsplit

from redis import Redis

from app.adapters.youtube_upload import ProviderFailure


class FixtureYouTube:
    def __init__(self, settings):
        if settings.app_env != "test" or settings.youtube_client_id != "fake-integration-client":
            raise RuntimeError("Test fixture configuration required")
        self.redis_url = settings.redis_url

    def exchange(self, code, verifier):
        if code != "fixture-code":
            raise ProviderFailure("OAUTH_DENIED")
        return {"refresh_token": "fixture-refresh"}, {
            "id": "fixture-channel",
            "title": "테스트 채널",
        }

    def access_token(self, credentials):
        assert credentials["refresh_token"] == "fixture-refresh"
        return "fixture-access"

    def channel(self, token):
        return {"id": "fixture-channel", "title": "테스트 채널"}

    def initiate(self, token, upload, size):
        with Redis.from_url(self.redis_url) as client:
            client.hincrby(f"sns-fixture:{upload.id}", "initiated", 1)
            client.hset(
                f"sns-fixture:{upload.id}",
                mapping={"title": upload.title, "privacy": upload.privacy},
            )
        return f"https://www.googleapis.com/upload/youtube/v3/videos?upload_id={upload.id}"

    def send(self, token, uri, stream, size):
        upload_id = parse_qs(urlsplit(uri).query)["upload_id"][0]
        assert len(stream.read()) == size
        with Redis.from_url(self.redis_url) as client:
            key = f"sns-fixture:{upload_id}"
            client.hincrby(key, "sent", 1)
            title = client.hget(key, "title").decode()
            if title.startswith("fixture-reject"):
                raise ProviderFailure("PROVIDER_REJECTED")
            if not title.startswith("fixture-incomplete"):
                client.hset(key, "remote_id", "abcdefghijk")
            if title.startswith(("fixture-unknown", "fixture-incomplete")):
                raise ProviderFailure("PROVIDER_UNREACHABLE", ambiguous=True)
        return "abcdefghijk"

    def probe(self, token, uri, size):
        upload_id = parse_qs(urlsplit(uri).query)["upload_id"][0]
        with Redis.from_url(self.redis_url) as client:
            key = f"sns-fixture:{upload_id}"
            client.hincrby(key, "probed", 1)
            remote = client.hget(key, "remote_id")
        return remote.decode() if remote else None
