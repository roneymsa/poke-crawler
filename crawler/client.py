"""Cliente HTTP para requisições à Bulbapedia com retries e conexão persistente."""

from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from crawler.domain.exceptions import FetchError

BASE_URL = "https://bulbapedia.bulbagarden.net"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3


def _make_retry_decorator(max_retries: int = DEFAULT_RETRIES):
    """Decorator tenacity: retenta apenas em erros de rede/timeout."""
    return retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )


class BulbapediaClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
        headers: Optional[dict] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._headers = headers or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self._async_client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._headers,
            follow_redirects=True,
        )
        self._sync_client = httpx.Client(
            timeout=self.timeout,
            headers=self._headers,
            follow_redirects=True,
        )

    def _build_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        path = path.lstrip("/")
        return f"{self.base_url}/{path}"

    async def get_page(self, path_or_url: str) -> str:
        url = self._build_url(path_or_url)

        @_make_retry_decorator(self.max_retries)
        async def _fetch() -> str:
            try:
                response = await self._async_client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                raise FetchError(url, str(e), status_code=code) from e
            except httpx.HTTPError as e:
                raise FetchError(url, str(e)) from e

        return await _fetch()

    def get_page_sync(self, path_or_url: str) -> str:
        """Versão síncrona de get_page (conexão persistente)."""
        url = self._build_url(path_or_url)

        @_make_retry_decorator(self.max_retries)
        def _fetch() -> str:
            try:
                response = self._sync_client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                raise FetchError(url, str(e), status_code=code) from e
            except httpx.HTTPError as e:
                raise FetchError(url, str(e)) from e

        return _fetch()

    def get_json_sync(self, path_or_url: str) -> Any:
        """GET e retorna o corpo como JSON (list ou dict). Levanta FetchError em falha."""
        url = self._build_url(path_or_url)

        @_make_retry_decorator(self.max_retries)
        def _fetch() -> Any:
            try:
                response = self._sync_client.get(url)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise FetchError(url, str(e), status_code=e.response.status_code) from e
            except (httpx.HTTPError, ValueError) as e:
                raise FetchError(url, str(e)) from e

        return _fetch()

    async def get_bytes(
        self, path_or_url: str, headers: Optional[dict] = None
    ) -> tuple[bytes, str]:
        """Baixa URL e retorna (corpo, content_type). Headers opcionais sobrescrevem os default."""
        url = self._build_url(path_or_url)
        request_headers = {**self._headers, **(headers or {})}

        @_make_retry_decorator(self.max_retries)
        async def _fetch() -> tuple[bytes, str]:
            try:
                response = await self._async_client.get(url, headers=request_headers)
                response.raise_for_status()
                ct = response.headers.get("content-type", "").split(";")[0].strip()
                return (response.content, ct)
            except httpx.HTTPError as e:
                raise FetchError(url, str(e)) from e

        return await _fetch()

    def get_bytes_sync(
        self, path_or_url: str, headers: Optional[dict] = None
    ) -> tuple[bytes, str]:
        """Versão síncrona de get_bytes."""
        url = self._build_url(path_or_url)
        request_headers = {**self._headers, **(headers or {})}

        @_make_retry_decorator(self.max_retries)
        def _fetch() -> tuple[bytes, str]:
            try:
                response = self._sync_client.get(url, headers=request_headers)
                response.raise_for_status()
                ct = response.headers.get("content-type", "").split(";")[0].strip()
                return (response.content, ct)
            except httpx.HTTPError as e:
                raise FetchError(url, str(e)) from e

        return _fetch()

    def close(self) -> None:
        """Fecha os clientes HTTP (sync). Use com context manager ou ao terminar."""
        self._sync_client.close()

    async def aclose(self) -> None:
        """Fecha os clientes HTTP (async + sync). Chame ao terminar o uso."""
        await self._async_client.aclose()
        self._sync_client.close()

    def __enter__(self) -> "BulbapediaClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    async def __aenter__(self) -> "BulbapediaClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
