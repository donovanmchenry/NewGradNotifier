"""HTTP helpers with caching, retries, and polite rate limiting."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from newgrad_notifier.utils.hashing import sha256_text


class CachedHttpClient:
    """Simple HTTP client with file caching and basic per-domain throttling."""

    def __init__(
        self,
        cache_dir: Path,
        timeout_seconds: float = 20.0,
        user_agent: str = "newgrad-notifier/0.1.0",
        min_domain_interval_seconds: float = 1.0,
        cache_ttl_seconds: int = 60 * 60 * 6,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.min_domain_interval_seconds = min_domain_interval_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._last_request_at: dict[str, float] = {}
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent},
        )
        self.logger = logging.getLogger(__name__)

    def close(self) -> None:
        """Close underlying resources."""

        self._client.close()

    def _cache_path(self, method: str, url: str, extra: str = "") -> Path:
        cache_key = sha256_text(f"{method}:{url}:{extra}")
        return self.cache_dir / f"{cache_key}.cache"

    def _is_cache_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age_seconds = time.time() - path.stat().st_mtime
        return age_seconds <= self.cache_ttl_seconds

    def _read_file_url(self, url: str) -> str:
        parsed = urlparse(url)
        file_path = Path(parsed.path if parsed.scheme == "file" else url)
        return file_path.read_text(encoding="utf-8")

    def _throttle(self, url: str) -> None:
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return
        previous = self._last_request_at.get(domain)
        if previous is None:
            self._last_request_at[domain] = time.time()
            return
        elapsed = time.time() - previous
        if elapsed < self.min_domain_interval_seconds:
            time.sleep(self.min_domain_interval_seconds - elapsed)
        self._last_request_at[domain] = time.time()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self._throttle(url)
        return self._client.request(method, url, json=json_body, params=params, headers=headers, data=data)

    def get_text(
        self,
        url: str,
        *,
        use_cache: bool = True,
        render_js: bool = False,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Fetch a text response from either a local file or HTTP endpoint."""

        if url.startswith("file://") or "://" not in url:
            return self._read_file_url(url)
        if render_js:
            return self.get_text_with_browser(url)

        extra = json.dumps({"method": method, "params": params, "data": data}, sort_keys=True)
        cache_path = self._cache_path(method, url, extra=extra)
        if use_cache and self._is_cache_fresh(cache_path):
            return cache_path.read_text(encoding="utf-8")

        response = self._request(method, url, params=params, headers=headers, data=data)
        response.raise_for_status()
        text = response.text
        cache_path.write_text(text, encoding="utf-8")
        return text

    def get_json(
        self,
        url: str,
        *,
        use_cache: bool = True,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Fetch a JSON payload from either a local file or HTTP endpoint."""

        extra = json.dumps({"json_body": json_body, "params": params}, sort_keys=True)
        cache_path = self._cache_path(method, url, extra=extra)
        if (url.startswith("file://") or "://" not in url) and method.upper() == "GET":
            return json.loads(self._read_file_url(url))
        if use_cache and self._is_cache_fresh(cache_path):
            return json.loads(cache_path.read_text(encoding="utf-8"))

        response = self._request(method, url, json_body=json_body, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def get_text_with_browser(self, url: str) -> str:
        """Fetch a page with Playwright for JS-heavy sources when explicitly requested."""

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is required for JS rendering but is not installed.") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=int(self.timeout_seconds * 1000))
                return page.content()
            finally:
                browser.close()
