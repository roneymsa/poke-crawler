"""Download de imagens dos Pokémon para pasta local."""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from crawler.domain.models import Pokemon

if TYPE_CHECKING:
    from crawler.client import BulbapediaClient

logger = logging.getLogger(__name__)

IMAGE_HEADERS = {
    "Accept": "image/*",
    "Referer": "https://bulbapedia.bulbagarden.net/",
}

def _extension_from_content_type(content_type: str) -> str:
    """Retorna extensão baseada no Content-Type (ex.: image/png → .png)."""
    content_type = (content_type or "").lower().split(";")[0].strip()
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "webp" in content_type:
        return ".webp"
    return ".img"


class ImageDownloader:
    """Usa o mesmo BulbapediaClient (com headers de imagem) para reutilizar conexão."""

    def __init__(
        self,
        images_dir: str = "images",
        client: Optional["BulbapediaClient"] = None,
    ):
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._client = client

    def _safe_filename(self, name: str) -> str:
        s = re.sub(r"[^\w\s-]", "", name)
        s = re.sub(r"[-\s]+", "_", s).strip("_")
        return s or "unknown"

    def _path_for_pokemon(self, pokemon: Pokemon, content_type: str) -> Path:
        name = self._safe_filename(pokemon.name)
        ext = _extension_from_content_type(content_type)
        return self.images_dir / f"{name}{ext}"

    def _existing_path_for_pokemon(self, pokemon: Pokemon) -> Optional[Path]:
        name = self._safe_filename(pokemon.name)
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = self.images_dir / f"{name}{ext}"
            if p.exists():
                return p
        return None

    def download(self, image_url: str, pokemon: Pokemon) -> Optional[str]:
        if not self._client:
            logger.warning("ImageDownloader sem client configurado (use download_async com client).")
            return None
        if not image_url or not image_url.startswith("http"):
            return None
        existing = self._existing_path_for_pokemon(pokemon)
        if existing is not None:
            return str(existing)
        try:
            content, content_type = self._client.get_bytes_sync(image_url, headers=IMAGE_HEADERS)
            if not content_type.startswith("image/"):
                logger.warning("URL não é imagem (content-type=%s): %s", content_type, image_url)
                return None
            path = self._path_for_pokemon(pokemon, content_type)
            path.write_bytes(content)
            return str(path)
        except Exception as e:
            logger.warning("Erro ao baixar %s: %s", image_url, e)
            return None

    async def download_async(self, image_url: str, pokemon: Pokemon) -> Optional[str]:
        """
        Usa o mesmo BulbapediaClient com headers de imagem (Accept: image/*).
        """
        if not self._client:
            logger.warning("ImageDownloader sem client configurado.")
            return None
        if not image_url or not image_url.startswith("http"):
            return None
        existing = self._existing_path_for_pokemon(pokemon)
        if existing is not None:
            return str(existing)
        try:
            content, content_type = await self._client.get_bytes(image_url, headers=IMAGE_HEADERS)
            if not content_type.startswith("image/"):
                logger.warning("URL não é imagem (content-type=%s): %s", content_type, image_url)
                return None
            path = self._path_for_pokemon(pokemon, content_type)
            path.write_bytes(content)
            return str(path)
        except Exception as e:
            logger.warning("Erro ao baixar %s: %s", image_url, e)
            return None
