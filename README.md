# Robots-Compliant Crawler

`robots.txt` 규칙과 crawl-delay를 준수하며 Selenium으로 웹 페이지를 수집하고,
진행 상황을 UI로 보여주는 프로젝트입니다.

## 현재 기본셋팅

- Python 3.10 이상 3.13 미만
- FastAPI + Uvicorn
- Selenium 4
- SQLite 저장소 준비
- Ruff, pytest 개발 도구
- 환경 설정은 `.env`로 관리
- `robots.txt` 정책 및 crawl-delay 엔진
- Selenium 단일 페이지 크롤러와 내부 링크 추출

## Windows 시작하기

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

브라우저에서 <http://127.0.0.1:8000/docs>를 엽니다.

## 현재 구현 범위

`app/crawler/policy.py`는 HTTPS와 허용 호스트를 확인하고, `robots.txt`를
불러오지 못하면 안전하게 중단합니다. `app/crawler/engine.py`는 허용된 URL만
Selenium으로 열고, 페이지 제목·본문 미리보기·동일 호스트 링크를 반환합니다.
`/products` 페이지에서는 상품명, 가격, 설명, 상품 URL, 이미지 URL도 추출합니다.

`app/crawler/ai_crawler.py`는 Selenium으로 HTML을 가져온 뒤 AI 모델(Qwen 등)에
분석을 요청해 제품 정보를 추출합니다. 기존 CSS 셀렉터 기반 추출과 달리 페이지
구조가 바뀌어도 AI가 유연하게 대응합니다.

`app/crawler/jobs.py`와 `/api/crawl-jobs`는 크롤링 작업 생성·시작·중지·상태
조회를 제공합니다. <http://127.0.0.1:8000/>에서 간단한 진행률 UI를 사용할 수
있습니다.

각 작업의 결과는 `artifacts/{job_id}.txt`에 UTF-8 텍스트로 누적 저장되며,
UI의 **저장 결과 보기** 버튼 또는 아래 API로 확인할 수 있습니다.

AI 모드를 사용하려면 `.env`에 `AI_API_URL`, `AI_API_KEY`, `AI_JWT_TOKEN`,
`AI_MODEL_ID`를 설정하고, API 호출 시 `use_ai: true`를 전달합니다.
`AI_JWT_TOKEN`은 `Authorization: Bearer`로, `AI_API_KEY`는 `X-API-Key`로
전달됩니다. 비밀값은 `.env`에만 저장하고 저장소에 커밋하지 않습니다.

```text
POST /api/crawl-jobs              # 기본 Selenium 방식
POST /api/crawl-jobs              # {"start_url": "...", "max_pages": 5, "use_ai": true}
POST /api/crawl-jobs/{job_id}/start
POST /api/crawl-jobs/{job_id}/stop
GET  /api/crawl-jobs/{job_id}
GET  /api/crawl-jobs/{job_id}/result.txt
```

## 검증

```powershell
python -m ruff check .
python -m pytest
```

## 개발 원칙

- 크롤링 전에 반드시 대상 사이트의 `robots.txt`를 확인합니다.
- `robots.txt` 파싱 실패 시 안전을 위해 크롤링을 시작하지 않습니다.
- 기본 대상 호스트는 `web-scraping.dev`로 제한합니다.
- CAPTCHA, 차단 페이지, 인증 장치를 우회하지 않습니다.
- 비밀값과 로컬 데이터베이스 파일은 저장소에 커밋하지 않습니다.
