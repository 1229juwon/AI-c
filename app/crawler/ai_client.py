from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a product data extraction assistant. "
    "Analyze the HTML content below and extract all product information. "
    "Return a JSON array of objects with these fields: "
    "name (string), price (string), description (string), url (string), image_url (string). "
    "If no products are found, return an empty array. "
    "Only return valid JSON ??no markdown fences, no explanations."
)

USER_PROMPT_TEMPLATE = """
Base URL: {base_url}
HTML Content (truncated to 15000 chars):
{html_content}

Extract all products from this page.
"""


@dataclass(frozen=True)
class AiConfig:
    api_url: str
    api_key: str
    model_id: str
    jwt_token: str = ""
    max_output_tokens: int = 16000
    timeout_seconds: int = 60


@dataclass(frozen=True)
class AiTrace:
    """Prompt and model output captured for displaying an AI extraction."""

    system_prompt: str
    user_prompt: str
    response: str


class AiClient:
    """HTTP client for the chat-completions API (OpenAI-compatible)."""

    def __init__(self, config: AiConfig) -> None:
        self._config = config
        self.last_trace: AiTrace | None = None

    def extract_products(self, html_content: str, base_url: str) -> list[dict[str, str]]:
        """Send HTML to the AI model and parse the product JSON response."""
        user_message = USER_PROMPT_TEMPLATE.format(
            base_url=base_url,
            html_content=html_content[:15000],
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        payload: dict[str, Any] = {
            "model": self._config.model_id,
            "messages": messages,
            "max_tokens": self._config.max_output_tokens,
            "temperature": 0.1,
        }

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self._config.api_key,
        }
        self.last_trace = AiTrace(SYSTEM_PROMPT, user_message, "")
        if self._config.jwt_token:
            headers["Authorization"] = "Bearer " + self._config.jwt_token

        try:
            with httpx.Client(timeout=self._config.timeout_seconds) as client:
                response = client.post(
                    self._config.api_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                raw_response = response.text
                body = response.json()
        except httpx.HTTPStatusError as exc:
            self.last_trace = self._trace_with_response(exc.response.text)
            logger.error("AI API HTTP error: %s", exc.response.text)
            return []
        except httpx.RequestError as exc:
            self.last_trace = self._trace_with_response(str(exc))
            logger.error("AI API request error: %s", exc)
            return []
        except (json.JSONDecodeError, KeyError) as exc:
            self.last_trace = self._trace_with_response(str(exc))
            logger.error("AI API response parse error: %s", exc)
            return []

        content = self._extract_content(body)
        self.last_trace = self._trace_with_response(content or raw_response)
        if not content:
            return []

        cleaned = self._clean_json_string(content)
        try:
            products = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("AI returned invalid JSON: %s", cleaned[:500])
            return []

        if not isinstance(products, list):
            logger.warning("AI response is not a JSON array")
            return []

        return products

    def _trace_with_response(self, response: str) -> AiTrace:
        trace = self.last_trace
        if trace is None:
            return AiTrace(SYSTEM_PROMPT, "", response)
        return AiTrace(trace.system_prompt, trace.user_prompt, response)

    @staticmethod
    def _extract_content(body: dict[str, Any]) -> str | None:
        """Extract text content from the chat-completions response."""
        try:
            choices = body.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and isinstance(item.get("text"), str)
                    ]
                    return "".join(text_parts) or None
        except (AttributeError, TypeError):
            pass
        return None

    @staticmethod
    def _clean_json_string(raw: str) -> str:
        """Strip markdown code fences and whitespace from AI JSON output."""
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            # Remove first line (```json or ```) and last line (```)
            if len(lines) >= 2:
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                return "\n".join(lines).strip()
        return raw


