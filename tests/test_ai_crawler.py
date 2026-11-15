from dataclasses import dataclass
from unittest.mock import MagicMock

from app.crawler.ai_client import AiClient, AiConfig
from app.crawler.ai_crawler import AiCrawler
from app.crawler.policy import RobotsPolicy


@dataclass
class FakeElement:
    href: str | None = None
    text: str = ""
    children: dict[str, "FakeElement"] | None = None

    def get_attribute(self, name: str) -> str | None:
        return self.href if name == "href" else None

    def find_element(self, by: str, value: str) -> "FakeElement":
        if self.children is None:
            raise AssertionError(f"Unexpected child selector: {value}")
        return self.children[value]


class FakeAiDriver:
    title = "AI Products"
    current_url = ""
    page_source = "<html><body>test</body></html>"

    def __init__(self) -> None:
        self.loaded_url = ""
        self.quit_called = False

    def set_page_load_timeout(self, timeout: int) -> None:
        pass

    def get(self, url: str) -> None:
        self.loaded_url = url

    def find_element(self, by: str, value: str) -> FakeElement:
        return FakeElement(text="  AI page  ")

    def find_elements(self, by: str, value: str) -> list[FakeElement]:
        if value == "a[href]":
            return [
                FakeElement(href="/product/1"),
                FakeElement(href="https://example.com/other"),
            ]
        return []

    def quit(self) -> None:
        self.quit_called = True


def make_policy() -> RobotsPolicy:
    from urllib.robotparser import RobotFileParser

    robot_parser = RobotFileParser()
    robot_parser.parse(["User-agent: *", "Disallow: /robots-disallowed"])
    return RobotsPolicy(
        allowed_host="web-scraping.dev",
        user_agent="TestCrawler/0.1",
        parser=robot_parser,
        delay_seconds=0,
    )


def _make_fake_ai_client(products: list[dict]) -> AiClient:
    config = AiConfig(
        api_url="http://localhost:8088/api/chat/completions",
        api_key="test-key",
        model_id="Qwen3.6-35B-A3B",
    )
    client = AiClient(config)
    client.extract_products = MagicMock(return_value=products)  # type: ignore[method-assign]
    return client


def test_ai_crawler_extracts_products_from_ai_response() -> None:
    driver = FakeAiDriver()
    ai_client = _make_fake_ai_client(
        [
            {
                "name": "AI Product",
                "price": "29.99",
                "description": "Extracted by AI",
                "url": "/product/ai",
                "image_url": "/img/ai.webp",
            }
        ]
    )
    crawler = AiCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        ai_client=ai_client,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/products")

    assert result.status == "success"
    assert len(result.products) == 1
    assert result.products[0].name == "AI Product"
    assert result.products[0].price == "29.99"
    assert result.products[0].url == "https://web-scraping.dev/product/ai"
    assert driver.quit_called


def test_ai_crawler_skips_robots_disallowed() -> None:
    driver = FakeAiDriver()
    ai_client = _make_fake_ai_client([])
    crawler = AiCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        ai_client=ai_client,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/robots-disallowed")

    assert result.status == "skipped_robots"
    assert driver.loaded_url == ""
    assert not driver.quit_called


def test_ai_crawler_handles_empty_ai_response() -> None:
    driver = FakeAiDriver()
    ai_client = _make_fake_ai_client([])
    crawler = AiCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        ai_client=ai_client,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/products")

    assert result.status == "success"
    assert len(result.products) == 0


def test_ai_crawler_filters_invalid_products() -> None:
    driver = FakeAiDriver()
    ai_client = _make_fake_ai_client(
        [
            {"name": "", "price": "1.00", "description": "", "url": "", "image_url": ""},
            {"name": "Valid", "price": "5.00", "description": "OK", "url": "/v", "image_url": ""},
        ]
    )
    crawler = AiCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        ai_client=ai_client,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/products")

    assert len(result.products) == 1
    assert result.products[0].name == "Valid"


def test_ai_crawler_resolves_relative_urls() -> None:
    driver = FakeAiDriver()
    ai_client = _make_fake_ai_client(
        [
            {
                "name": "Relative URL Product",
                "price": "10.00",
                "description": "Has relative URL",
                "url": "product/relative",
                "image_url": "img/relative.webp",
            }
        ]
    )
    crawler = AiCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        ai_client=ai_client,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/products")

    assert len(result.products) == 1
    assert result.products[0].url == "https://web-scraping.dev/product/relative"
    assert result.products[0].image_url == "img/relative.webp"