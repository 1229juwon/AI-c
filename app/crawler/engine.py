from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol
from urllib.parse import urldefrag, urljoin, urlsplit

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from app.crawler.policy import RobotsPolicy


class DriverLike(Protocol):
    title: str
    current_url: str

    def get(self, url: str) -> None: ...

    def find_element(self, by: str, value: str): ...

    def find_elements(self, by: str, value: str): ...

    def quit(self) -> None: ...


@dataclass(frozen=True)
class Product:
    name: str
    price: str
    description: str
    url: str
    image_url: str


@dataclass(frozen=True)
class PageResult:
    url: str
    status: str
    title: str
    content_preview: str
    links: tuple[str, ...]
    duration_ms: int
    products: tuple[Product, ...] = ()
    error_message: str | None = None


class SeleniumCrawler:
    def __init__(
        self,
        *,
        policy: RobotsPolicy,
        driver_factory: Callable[[], DriverLike],
        page_timeout_seconds: int,
    ) -> None:
        self._policy = policy
        self._driver_factory = driver_factory
        self._page_timeout_seconds = page_timeout_seconds

    def crawl_page(self, url: str) -> PageResult:
        normalized_url = urldefrag(url)[0]
        started = perf_counter()
        if not self._policy.can_fetch(normalized_url):
            return self._result(
                normalized_url,
                started,
                status="skipped_robots",
                error_message="URL is outside the allowed policy.",
            )

        driver = self._driver_factory()
        try:
            driver.set_page_load_timeout(self._page_timeout_seconds)
            self._policy.wait_for_request()
            driver.get(normalized_url)
            body = driver.find_element(By.TAG_NAME, "body").text
            links = self._same_host_links(driver, normalized_url)
            products = self._extract_products(driver, normalized_url)
            return self._result(
                normalized_url,
                started,
                status="success",
                title=driver.title,
                content_preview=" ".join(body.split())[:500],
                links=links,
                products=products,
            )
        except (TimeoutException, WebDriverException) as exc:
            return self._result(
                normalized_url,
                started,
                status="failed",
                error_message=str(exc),
            )
        finally:
            driver.quit()

    def _same_host_links(self, driver: DriverLike, base_url: str) -> tuple[str, ...]:
        base_host = urlsplit(base_url).hostname
        links: set[str] = set()
        for element in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
            href = element.get_attribute("href")
            if not href:
                continue
            absolute_url = urldefrag(urljoin(base_url, href))[0]
            parts = urlsplit(absolute_url)
            if parts.scheme == "https" and parts.hostname == base_host:
                links.add(absolute_url)
        return tuple(sorted(links))

    def _extract_products(
        self,
        driver: DriverLike,
        base_url: str,
    ) -> tuple[Product, ...]:
        if urlsplit(base_url).path != "/products":
            return ()

        products: list[Product] = []
        for card in driver.find_elements(By.CSS_SELECTOR, ".product"):
            name_element = card.find_element(By.CSS_SELECTOR, ".description h3 a")
            description_element = card.find_element(By.CSS_SELECTOR, ".short-description")
            price_element = card.find_element(By.CSS_SELECTOR, ".price")
            image_element = card.find_element(By.CSS_SELECTOR, ".thumbnail img")
            products.append(
                Product(
                    name=name_element.text.strip(),
                    price=price_element.text.strip(),
                    description=" ".join(description_element.text.split()),
                    url=urljoin(base_url, name_element.get_attribute("href") or ""),
                    image_url=image_element.get_attribute("src") or "",
                )
            )
        return tuple(products)

    @staticmethod
    def _result(
        url: str,
        started: float,
        *,
        status: str,
        title: str = "",
        content_preview: str = "",
        links: tuple[str, ...] = (),
        products: tuple[Product, ...] = (),
        error_message: str | None = None,
    ) -> PageResult:
        return PageResult(
            url=url,
            status=status,
            title=title,
            content_preview=content_preview,
            links=links,
            duration_ms=round((perf_counter() - started) * 1000),
            products=products,
            error_message=error_message,
        )


def create_chrome_driver(*, headless: bool, user_agent: str) -> WebDriver:
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    options.add_argument(f"--user-agent={user_agent}")
    return ChromeDriver(options=options)
