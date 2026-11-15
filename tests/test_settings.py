from app.config import Settings


def test_environment_overrides_local_defaults(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://broker:6379/4")
    monkeypatch.setenv("APP_ENV", "test")
    settings = Settings(_env_file=None)
    assert settings.redis_url == "redis://broker:6379/4"
    assert settings.app_env == "test"
