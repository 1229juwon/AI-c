from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.crawler.jobs import CrawlJobManager

router = APIRouter(prefix="/api/crawl-jobs", tags=["crawl jobs"])
settings = get_settings()
manager = CrawlJobManager(
    user_agent=settings.crawler_user_agent,
    default_delay_seconds=settings.crawler_default_delay_seconds,
    page_timeout_seconds=settings.crawler_page_timeout_seconds,
    headless=settings.selenium_headless,
    results_dir=settings.results_dir,
)


class CreateJobRequest(BaseModel):
    start_url: str = "https://web-scraping.dev/products"
    max_pages: int = Field(default=10, ge=1, le=100)


@router.post("", status_code=201)
def create_job(request: CreateJobRequest) -> dict[str, object]:
    try:
        job = manager.create_job(request.start_url, request.max_pages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.snapshot(job.id)


@router.post("/{job_id}/start")
def start_job(job_id: str) -> dict[str, object]:
    try:
        manager.start_job(job_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.snapshot(job_id)


@router.post("/{job_id}/stop")
def stop_job(job_id: str) -> dict[str, object]:
    try:
        manager.stop_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return manager.snapshot(job_id)


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    try:
        return manager.snapshot(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/result.txt", response_class=PlainTextResponse)
def get_result_file(job_id: str) -> str:
    try:
        return manager.read_results(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
