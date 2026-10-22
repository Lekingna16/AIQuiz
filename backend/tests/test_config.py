from app.config import Settings


def test_release_debug_value_is_treated_as_production(monkeypatch):
    """A hosting provider's DEBUG=release must not stop the API at startup."""
    monkeypatch.setenv("DEBUG", "release")

    assert Settings().DEBUG is False


def test_development_debug_value_is_treated_as_enabled(monkeypatch):
    monkeypatch.setenv("DEBUG", "development")

    assert Settings().DEBUG is True
