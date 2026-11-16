from app.services import sns
from app.worker import celery_app
from tests.integration.fixture_sns_provider import FixtureYouTube


def main():
    sns.YouTubeProvider = FixtureYouTube
    celery_app.worker_main(["worker", "--loglevel=INFO", "--concurrency=1", "-Q", "sns"])


if __name__ == "__main__":
    main()
