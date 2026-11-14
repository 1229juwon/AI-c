from dataclasses import dataclass

from app.crawler.engine import SeleniumCrawler
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


class FakeDriver:
    title = "Products"
    current_url = ""

    def __init__(self) -> None:
        self.loaded_url = ""
        self.quit_called = False

    def set_page_load_timeout(self, timeout: int) -> None:
        pass

    def get(self, url: str) -> None:
        self.loaded_url = url

    def find_element(self, by: str, value: str) -> FakeElement:
        return FakeElement(text="  Product page  ")

    def find_elements(self, by: str, value: str) -> list[FakeElement]:
        if value == ".product":
            return []
        return [
            FakeElement(href="/product/2"),
            FakeElement(href="https://example.com/outside"),
            FakeElement(href="#details"),
        ]

    def quit(self) -> None:
        self.quit_called = True


class ProductDriver(FakeDriver):
    def find_elements(self, by: str, value: str) -> list[FakeElement]:
        if value == ".product":
            return [
                FakeElement(
                    children={
                        ".description h3 a": FakeElement(
                            href="https://web-scraping.dev/product/1",
                            text="Box of Chocolate Candy",
                        ),
                        ".short-description": FakeElement(
                            text="A box of rich chocolate.",
                        ),
                        ".price": FakeElement(text="24.99"),
                        ".thumbnail img": FakeElement(
                            href="https://web-scraping.dev/assets/chocolate.webp",
                        ),
                    }
                )
            ]
        return super().find_elements(by, value)


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


def test_crawler_extracts_only_same_host_links() -> None:
    driver = FakeDriver()
    crawler = SeleniumCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/products#top")

    assert result.status == "success"
    assert result.url == "https://web-scraping.dev/products"
    assert result.content_preview == "Product page"
    assert result.links == (
        "https://web-scraping.dev/product/2",
        "https://web-scraping.dev/products",
    )
    assert driver.quit_called


def test_crawler_does_not_open_disallowed_url() -> None:
    driver = FakeDriver()
    crawler = SeleniumCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/robots-disallowed")

    assert result.status == "skipped_robots"
    assert driver.loaded_url == ""
    assert not driver.quit_called


def test_crawler_extracts_products_from_products_page() -> None:
    driver = ProductDriver()
    crawler = SeleniumCrawler(
        policy=make_policy(),
        driver_factory=lambda: driver,
        page_timeout_seconds=10,
    )

    result = crawler.crawl_page("https://web-scraping.dev/products?page=1")

    assert len(result.products) == 1
    assert result.products[0].name == "Box of Chocolate Candy"
    assert result.products[0].price == "24.99"


def test_policy_enforces_request_delay() -> None:
    policy = make_policy()
    policy.delay_seconds = 2
    clock = iter([100.0, 100.5, 100.5, 102.0])
    sleeps: list[float] = []

    policy.wait_for_request(sleep=sleeps.append, monotonic=lambda: next(clock))
    policy.wait_for_request(sleep=sleeps.append, monotonic=lambda: next(clock))

    assert sleeps == [1.5]
