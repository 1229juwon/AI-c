from __future__ import annotations

import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By

from app.crawler.ai_client import AiClient
from app.crawler.engine import DriverLike, PageResult, Product
from app.crawler.policy import RobotsPolicy

logger = logging.getLogger(__name__)


class AiCrawler:
    """Selenium-based crawler that uses AI to analyze HTML and extract product info."""

    def __init__(
        self,
        *,
        policy: RobotsPolicy,
        driver_factory: Callable[[], DriverLike],
        ai_client: AiClient,
        page_timeout_seconds: int,
    ) -> None:
        self._policy = policy
        self._driver_factory = driver_factory
        self._ai_client = ai_client
        self._page_timeout_seconds = page_timeout_seconds

    def crawl_page(self, url: str) -> PageResult:
        """Crawl a single page using Selenium + AI analysis."""
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

            body_text = driver.find_element(By.TAG_NAME, "body").text
            links = self._same_host_links(driver, normalized_url)

            # Get raw HTML for AI analysis
            html_content = driver.page_source
            title = driver.title

            # Use AI to extract products
            products, ai_prompt, ai_response = self._extract_products_with_ai(
                html_content, normalized_url
            )

            return self._result(
                normalized_url,
                started,
                status="success",
                title=title,
                content_preview=" ".join(body_text.split())[:500],
                links=links,
                products=products,
                ai_prompt=ai_prompt,
                ai_response=ai_response,
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

    def _extract_products_with_ai(
        self,
        html_content: str,
        base_url: str,
    ) -> tuple[tuple[Product, ...], str, str]:
        """Send HTML to AI and convert the response to Product objects."""
        try:
            raw_products = self._ai_client.extract_products(html_content, base_url)
        except Exception as exc:  # pragma: no cover
            logger.error("AI extraction failed: %s", exc)
            return (), "", str(exc)

        trace = self._ai_client.last_trace

        products: list[Product] = []
        for raw in raw_products:
            product = self._normalize_product(raw, base_url)
            if product and self._is_valid_product(product):
                products.append(product)

        if trace is None:
            return tuple(products), "", ""
        prompt = f"System:\n{trace.system_prompt}\n\nUser:\n{trace.user_prompt}"
        return tuple(products), prompt, trace.response

    @staticmethod
    def _normalize_product(raw: dict[str, Any], base_url: str) -> Product | None:
        """Normalize a raw AI response dict into a Product, resolving relative URLs."""
        try:
            name = str(raw.get("name", "")).strip()
            if not name:
                return None
            return Product(
                name=name,
                price=str(raw.get("price", "")).strip(),
                description=" ".join(str(raw.get("description", "")).split()),
                url=urljoin(base_url, str(raw.get("url", ""))),
                image_url=str(raw.get("image_url", "")).strip(),
            )
        except (AttributeError, TypeError):
            return None

    @staticmethod
    def _is_valid_product(product: Product) -> bool:
        """Check that a product has at least a name."""
        return bool(product.name)

    @staticmethod
    def _same_host_links(driver: DriverLike, base_url: str) -> tuple[str, ...]:
        """Extract same-host links from the page."""
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
        ai_prompt: str = "",
        ai_response: str = "",
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
            ai_prompt=ai_prompt,
            ai_response=ai_response,
        )