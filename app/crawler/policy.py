from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser


class RobotsPolicyError(RuntimeError):
    """Raised when robots.txt cannot be loaded or parsed safely."""


@dataclass
class RobotsPolicy:
    allowed_host: str
    user_agent: str
    parser: RobotFileParser
    delay_seconds: float
    _last_request_at: float | None = None
    _lock: Lock = field(default_factory=Lock)

    @classmethod
    def load(
        cls,
        *,
        base_url: str,
        user_agent: str,
        default_delay_seconds: float,
        timeout_seconds: int = 10,
    ) -> RobotsPolicy:
        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.hostname:
            raise RobotsPolicyError("The base URL must use HTTPS and include a hostname.")

        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        request = Request(robots_url, headers={"User-Agent": user_agent})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                status = getattr(response, "status", response.getcode())
                if status < 200 or status >= 300:
                    raise RobotsPolicyError(f"robots.txt returned HTTP {status}.")
                contents = response.read().decode("utf-8")
        except (OSError, UnicodeDecodeError, URLError) as exc:
            raise RobotsPolicyError(f"Unable to load robots.txt: {exc}") from exc

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(contents.splitlines())
        declared_delay = parser.crawl_delay(user_agent)
        delay_seconds = max(
            default_delay_seconds,
            float(declared_delay) if declared_delay is not None else 0.0,
        )
        return cls(
            allowed_host=parts.hostname.lower(),
            user_agent=user_agent,
            parser=parser,
            delay_seconds=delay_seconds,
        )

    def can_fetch(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname is None:
            return False
        if parts.hostname.lower() != self.allowed_host:
            return False
        return self.parser.can_fetch(self.user_agent, url)

    def wait_for_request(self, sleep=time.sleep, monotonic=time.monotonic) -> None:
        with self._lock:
            now = monotonic()
            if self._last_request_at is not None:
                remaining = self.delay_seconds - (now - self._last_request_at)
                if remaining > 0:
                    sleep(remaining)
                    now = monotonic()
            self._last_request_at = now
