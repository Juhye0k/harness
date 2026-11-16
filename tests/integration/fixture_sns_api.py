"""Only this test entrypoint replaces OAuth; production always uses real adapter."""

from app.main import app  # noqa: F401
from app.services import sns
from tests.integration.fixture_sns_provider import FixtureYouTube

sns.YouTubeProvider = FixtureYouTube
