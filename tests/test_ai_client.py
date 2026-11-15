from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from app.crawler.ai_client import AiClient, AiConfig


@contextmanager
def _make_client(mock_body: dict):
    config = AiConfig(
        api_url="http://localhost:8088/api/chat/completions",
        api_key="test-key",
        model_id="Qwen3.6-35B-A3B",
    )
    client = AiClient(config)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=mock_body)

    mock_http_client = MagicMock()
    mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
    mock_http_client.__exit__ = MagicMock(return_value=False)
    mock_http_client.post = MagicMock(return_value=mock_response)

    with patch("httpx.Client", return_value=mock_http_client):
        yield client


def test_extract_products_parses_ai_response() -> None:
    mock_body = {
        "choices": [
            {
                "message": {
                    "content": (
                        '[{"name":"Test Product","price":"19.99",'
                        '"description":"A test.","url":"/product/1",'
                        '"image_url":"/img/test.webp"}]'
                    )
                }
            }
        ]
    }
    with _make_client(mock_body) as client:
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert len(products) == 1
    assert products[0]["name"] == "Test Product"
    assert products[0]["price"] == "19.99"


def test_extract_products_captures_ai_response_trace() -> None:
    mock_body = {
        "choices": [{"message": {"content": '[{"name":"Traced Product"}]'}}]
    }
    with _make_client(mock_body) as client:
        client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert client.last_trace is not None
    assert "Traced Product" in client.last_trace.response


def test_extract_products_sends_jwt_and_api_key_headers() -> None:
    config = AiConfig(
        api_url="http://localhost:8088/api/chat/completions",
        api_key="test-key",
        jwt_token="test-jwt",
        model_id="Qwen3.6-35B-A3B",
    )
    client = AiClient(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = '{"choices":[{"message":{"content":"[]"}}]}'
    mock_response.json = MagicMock(return_value={"choices": [{"message": {"content": "[]"}}]})
    mock_http_client = MagicMock()
    mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
    mock_http_client.__exit__ = MagicMock(return_value=False)
    mock_http_client.post = MagicMock(return_value=mock_response)

    with patch("httpx.Client", return_value=mock_http_client):
        client.extract_products("<html>...</html>", "https://web-scraping.dev")

    request_headers = mock_http_client.post.call_args.kwargs["headers"]
    assert request_headers["Authorization"] == "Bearer test-jwt"
    assert request_headers["X-API-Key"] == "test-key"


def test_extract_products_supports_content_blocks() -> None:
    mock_body = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": '[{"name":"Block Product"}]'}
                    ]
                }
            }
        ]
    }
    with _make_client(mock_body) as client:
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert products[0]["name"] == "Block Product"


def test_extract_products_returns_empty_on_http_error() -> None:
    import httpx

    config = AiConfig(
        api_url="http://localhost:8088/api/chat/completions",
        api_key="test-key",
        model_id="Qwen3.6-35B-A3B",
    )
    client = AiClient(config)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
    )

    mock_http_client = MagicMock()
    mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
    mock_http_client.__exit__ = MagicMock(return_value=False)
    mock_http_client.post = MagicMock(return_value=mock_response)

    with patch("httpx.Client", return_value=mock_http_client):
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert products == []


def test_extract_products_returns_empty_on_request_error() -> None:
    import httpx

    config = AiConfig(
        api_url="http://localhost:8088/api/chat/completions",
        api_key="test-key",
        model_id="Qwen3.6-35B-A3B",
    )
    client = AiClient(config)

    mock_http_client = MagicMock()
    mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
    mock_http_client.__exit__ = MagicMock(return_value=False)
    mock_http_client.post = MagicMock(side_effect=httpx.ConnectError("fail"))

    with patch("httpx.Client", return_value=mock_http_client):
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert products == []


def test_extract_products_handles_markdown_json_fences() -> None:
    mock_body = {
        "choices": [
            {
                "message": {
                    "content": (
                        '```\n'
                        '[{"name":"Markdown Product","price":"9.99",'
                        '"description":"With fences.","url":"/p/1",'
                        '"image_url":"/img/p.webp"}]'
                        '\n```'
                    )
                }
            }
        ]
    }
    with _make_client(mock_body) as client:
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert len(products) == 1
    assert products[0]["name"] == "Markdown Product"


def test_extract_products_handles_json_markdown_fence() -> None:
    mock_body = {
        "choices": [
            {
                "message": {
                    "content": (
                        '```json\n'
                        '[{"name":"Json Fence","price":"5.00",'
                        '"description":"json tag.","url":"/p/2",'
                        '"image_url":"/img/p2.webp"}]'
                        '\n```'
                    )
                }
            }
        ]
    }
    with _make_client(mock_body) as client:
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert len(products) == 1
    assert products[0]["name"] == "Json Fence"


def test_extract_products_returns_empty_on_invalid_json() -> None:
    mock_body = {
        "choices": [
            {
                "message": {
                    "content": "This is not JSON at all"
                }
            }
        ]
    }
    with _make_client(mock_body) as client:
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert products == []


def test_extract_products_returns_empty_on_non_array_response() -> None:
    mock_body = {
        "choices": [
            {
                "message": {
                    "content": '{"name": "single"}'
                }
            }
        ]
    }
    with _make_client(mock_body) as client:
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert products == []


def test_extract_products_returns_empty_on_missing_choices() -> None:
    mock_body = {"choices": []}
    with _make_client(mock_body) as client:
        products = client.extract_products("<html>...</html>", "https://web-scraping.dev")

    assert products == []