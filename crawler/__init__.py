"""Poké-Crawler: extração de dados de Pokémon da Bulbapedia."""

from crawler.models import Pokemon
from crawler.client import BulbapediaClient
from crawler.parser import BulbapediaParser
from crawler.storage import Storage
from crawler.downloader import ImageDownloader

__all__ = [
    "Pokemon",
    "BulbapediaClient",
    "BulbapediaParser",
    "Storage",
    "ImageDownloader",
]
