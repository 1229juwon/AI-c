from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api import router as crawl_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Selenium crawler foundation with robots.txt compliance.",
    version="0.1.0",
)
app.include_router(crawl_router)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(Path(__file__).parent / "web" / "index.html")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/api/config", tags=["system"])
def public_config() -> dict[str, str | int | float | bool]:
    return {
        "app_name": settings.app_name,
        "allowed_host": "web-scraping.dev",
        "default_delay_seconds": settings.crawler_default_delay_seconds,
        "max_pages": settings.crawler_max_pages,
        "selenium_headless": settings.selenium_headless,
    }
