from app.config import Settings
from app.controllers.documents import _create_ai_service


def test_release_debug_value_is_treated_as_production(monkeypatch):
    """A hosting provider's DEBUG=release must not stop the API at startup."""
    monkeypatch.setenv("DEBUG", "release")

    assert Settings().DEBUG is False


def test_development_debug_value_is_treated_as_enabled(monkeypatch):
    monkeypatch.setenv("DEBUG", "development")

    assert Settings().DEBUG is True


def test_deepseek_is_default_for_answers_and_scans(monkeypatch):
    for name in ("AI_PROVIDER", "OCR_PROVIDER", "DEEPSEEK_MODEL", "DEEPSEEK_VISION_MODEL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None, DEEPSEEK_API_KEY="test-key")
    assert settings.AI_PROVIDER == settings.OCR_PROVIDER == "deepseek"
    assert settings.DEEPSEEK_VISION_MODEL == "deepseek-flash"
    service = _create_ai_service(settings)
    assert service.provider_name == "DeepSeek"
    assert service.model == settings.DEEPSEEK_MODEL
    assert str(service.client.base_url) == "https://api.deepseek.com"
