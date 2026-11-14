import time
from pathlib import Path
from urllib.robotparser import RobotFileParser

from app.crawler.engine import PageResult
from app.crawler.jobs import CrawlJobManager
from app.crawler.policy import RobotsPolicy


class FakeCrawler:
    def crawl_page(self, url: str) -> PageResult:
        return PageResult(
            url=url,
            status="success",
            title="Test page",
            content_preview="content",
            links=(),
            duration_ms=1,
        )


def fake_policy() -> RobotsPolicy:
    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /robots-disallowed"])
    return RobotsPolicy(
        allowed_host="web-scraping.dev",
        user_agent="TestCrawler/0.1",
        parser=parser,
        delay_seconds=0,
    )


def test_job_runs_with_injected_crawler(tmp_path: Path) -> None:
    manager = CrawlJobManager(
        policy_loader=lambda **kwargs: fake_policy(),
        crawler_factory=lambda policy: FakeCrawler(),
        results_dir=tmp_path,
    )
    job = manager.create_job("https://web-scraping.dev/products", max_pages=1)
    manager.start_job(job.id)

    deadline = time.monotonic() + 2
    snapshot = manager.snapshot(job.id)
    while snapshot["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = manager.snapshot(job.id)

    assert snapshot["status"] == "completed"
    assert snapshot["completed"] == 1
    assert snapshot["results"][0]["status"] == "success"
    result_file = tmp_path / f"{job.id}.txt"
    assert result_file.exists()
    assert "https://web-scraping.dev/products" in result_file.read_text(encoding="utf-8")
    assert "content" in manager.read_results(job.id)


def test_job_rejects_external_start_url() -> None:
    manager = CrawlJobManager()

    try:
        manager.create_job("https://example.com", max_pages=1)
    except ValueError as exc:
        assert "web-scraping.dev" in str(exc)
    else:
        raise AssertionError("Expected external URL to be rejected.")
