from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event, Lock
from urllib.parse import urlsplit
from uuid import uuid4

from app.crawler.ai_client import AiClient, AiConfig
from app.crawler.ai_crawler import AiCrawler
from app.crawler.engine import PageResult, SeleniumCrawler, create_chrome_driver
from app.crawler.policy import RobotsPolicy, RobotsPolicyError

logger = logging.getLogger(__name__)


@dataclass
class CrawlJob:
    id: str
    start_url: str
    max_pages: int
    status: str = "created"
    completed: int = 0
    queued: int = 1
    results: list[PageResult] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    error_message: str | None = None
    stop_event: Event = field(default_factory=Event, repr=False)


class CrawlJobManager:
    def __init__(
        self,
        *,
        policy_loader: Callable[..., RobotsPolicy] = RobotsPolicy.load,
        crawler_factory: Callable[[RobotsPolicy], SeleniumCrawler | AiCrawler] | None = None,
        user_agent: str = "RobotsCompliantCrawler/0.1",
        default_delay_seconds: float = 2.0,
        page_timeout_seconds: int = 30,
        headless: bool = True,
        results_dir: str | Path = "artifacts",
        ai_api_url: str = "",
        ai_api_key: str = "",
        ai_jwt_token: str = "",
        ai_model_id: str = "",
        ai_max_output_tokens: int = 16000,
        ai_timeout_seconds: int = 60,
    ) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self._jobs: dict[str, CrawlJob] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="crawler")
        self._policy_loader = policy_loader
        self._user_agent = user_agent
        self._default_delay_seconds = default_delay_seconds
        self._crawler_factory = crawler_factory or self._make_crawler_factory(
            page_timeout_seconds=page_timeout_seconds,
            headless=headless,
        )
        self._results_dir = Path(results_dir)
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._ai_config = AiConfig(
            api_url=ai_api_url,
            api_key=ai_api_key,
            jwt_token=ai_jwt_token,
            model_id=ai_model_id,
            max_output_tokens=ai_max_output_tokens,
            timeout_seconds=ai_timeout_seconds,
        )

    def create_job(self, start_url: str, max_pages: int) -> CrawlJob:
        return self.create_job_with_factory(start_url, max_pages, None)

    def create_job_with_factory(
        self, start_url: str, max_pages: int, crawler_factory
    ) -> CrawlJob:
        self._validate_start_url(start_url)
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1.")
        job = CrawlJob(id=str(uuid4()), start_url=start_url, max_pages=max_pages)
        job.events.append(f"Job created for {start_url}")
        with self._lock:
            self._jobs[job.id] = job
        job._crawler_factory = crawler_factory  # type: ignore[attr-defined]
        return job

    def start_job(self, job_id: str) -> CrawlJob:
        job = self._get_job(job_id)
        with self._lock:
            if job.status != "created":
                raise ValueError(f"Job is already {job.status}.")
            job.status = "running"
            job.events.append("Crawl started.")
        crawler_factory = getattr(job, "_crawler_factory", None) or self._crawler_factory
        self._executor.submit(self._run_job, job, crawler_factory)
        return job

    def stop_job(self, job_id: str) -> CrawlJob:
        job = self._get_job(job_id)
        job.stop_event.set()
        with self._lock:
            if job.status in {"created", "running"}:
                job.status = "stopping"
                job.events.append("Stop requested.")
        return job

    def get_job(self, job_id: str) -> CrawlJob:
        return self._get_job(job_id)

    def snapshot(self, job_id: str) -> dict[str, object]:
        job = self._get_job(job_id)
        with self._lock:
            return {
                "id": job.id,
                "start_url": job.start_url,
                "status": job.status,
                "max_pages": job.max_pages,
                "completed": job.completed,
                "queued": job.queued,
                "results": [asdict(result) for result in job.results],
                "events": list(job.events),
                "error_message": job.error_message,
                "result_file": self._result_path(job).name,
            }

    def read_results(self, job_id: str) -> str:
        job = self._get_job(job_id)
        path = self._result_path(job)
        if not path.exists():
            raise FileNotFoundError(f"Result file does not exist for job: {job_id}")
        return path.read_text(encoding="utf-8")

    def _run_job(self, job: CrawlJob, crawler_factory) -> None:
        try:
            parts = urlsplit(job.start_url)
            policy = self._policy_loader(
                base_url=f"{parts.scheme}://{parts.netloc}",
                user_agent=self._user_agent,
                default_delay_seconds=self._default_delay_seconds,
            )
            crawler = crawler_factory(policy)
            pending = deque([job.start_url])
            seen = {job.start_url}
            while pending and job.completed < job.max_pages and not job.stop_event.is_set():
                url = pending.popleft()
                result = crawler.crawl_page(url)
                with self._lock:
                    job.results.append(result)
                    job.completed += 1
                    job.queued = len(pending)
                    job.events.append(f"{result.status}: {result.url}")
                    self._write_results(job)
                for link in result.links:
                    if link not in seen and len(seen) < job.max_pages:
                        seen.add(link)
                        pending.append(link)
            with self._lock:
                job.status = "stopped" if job.stop_event.is_set() else "completed"
                job.queued = len(pending)
                self._write_results(job)
                job.events.append(f"Job {job.status}.")
        except RobotsPolicyError as exc:
            self._fail_job(job, str(exc))
        except (OSError, ValueError, RuntimeError) as exc:
            self._fail_job(job, str(exc))

    def _fail_job(self, job: CrawlJob, message: str) -> None:
        with self._lock:
            job.status = "failed"
            job.error_message = message
            job.events.append(f"Job failed: {message}")

    def _result_path(self, job: CrawlJob) -> Path:
        return self._results_dir / f"{job.id}.txt"

    def _write_results(self, job: CrawlJob) -> None:
        lines: list[str] = [
            "Robots-Compliant Crawler Results",
            f"Job ID: {job.id}",
            f"Start URL: {job.start_url}",
            f"Status: {job.status}",
            "",
        ]
        for index, result in enumerate(job.results, start=1):
            lines.extend(
                [
                    f"===== PAGE {index} =====",
                    f"URL: {result.url}",
                    f"Status: {result.status}",
                    f"Title: {result.title}",
                    f"Duration (ms): {result.duration_ms}",
                    f"Links: {len(result.links)}",
                ]
            )
            if result.error_message:
                lines.append(f"Error: {result.error_message}")
            for product in result.products:
                lines.extend(
                    [
                        "",
                        f"Product: {product.name}",
                        f"Price: {product.price}",
                        f"URL: {product.url}",
                        f"Image: {product.image_url}",
                        f"Description: {product.description}",
                    ]
                )
            lines.extend(["", "Content preview:", result.content_preview, ""])
        temporary_path = self._result_path(job).with_suffix(".tmp")
        temporary_path.write_text("\n".join(lines), encoding="utf-8")
        temporary_path.replace(self._result_path(job))

    def _get_job(self, job_id: str) -> CrawlJob:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise KeyError(f"Unknown crawl job: {job_id}") from exc

    @staticmethod
    def _validate_start_url(start_url: str) -> None:
        parts = urlsplit(start_url)
        if parts.scheme != "https" or parts.hostname != "web-scraping.dev":
            raise ValueError("Only https://web-scraping.dev URLs are supported.")

    @staticmethod
    def _make_crawler_factory(
        *,
        page_timeout_seconds: int,
        headless: bool,
    ) -> Callable[[RobotsPolicy], SeleniumCrawler]:
        def create_crawler(policy: RobotsPolicy) -> SeleniumCrawler:
            return SeleniumCrawler(
                policy=policy,
                driver_factory=lambda: create_chrome_driver(
                    headless=headless,
                    user_agent=policy.user_agent,
                ),
                page_timeout_seconds=page_timeout_seconds,
            )

        return create_crawler

    def make_ai_crawler_factory(
        self,
    ) -> Callable[[RobotsPolicy], AiCrawler]:
        """Create an AiCrawler factory when AI config is available."""
        if not self._ai_config.api_url or not (
            self._ai_config.api_key or self._ai_config.jwt_token
        ):
            raise ValueError(
                "AI crawler requires ai_api_url and an AI credential to be configured."
            )

        ai_client = AiClient(self._ai_config)

        def create_ai_crawler(policy: RobotsPolicy) -> AiCrawler:
            return AiCrawler(
                policy=policy,
                driver_factory=lambda: create_chrome_driver(
                    headless=True,
                    user_agent=self._user_agent,
                ),
                ai_client=ai_client,
                page_timeout_seconds=30,
            )

        return create_ai_crawler