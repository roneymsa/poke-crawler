"""Exceções de domínio do Poké-Crawler."""

from typing import Optional


class FetchError(Exception):
    """Erro ao obter a página (rede, timeout ou HTTP 4xx/5xx)."""

    def __init__(
        self,
        url: str,
        message: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        self.url = url
        self.status_code = status_code
        self.message = message or url
        super().__init__(self.message)
