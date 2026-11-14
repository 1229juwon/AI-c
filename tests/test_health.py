from app.main import health, public_config


def test_health() -> None:
    response = health()

    assert response["status"] == "ok"


def test_public_config_does_not_expose_secrets() -> None:
    response = public_config()

    assert response["allowed_host"] == "web-scraping.dev"
    assert "database_url" not in response
