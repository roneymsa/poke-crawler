"""
Resolução de nomes de Pokémon via API OpenSearch da Bulbapedia.
Retorna a URL da página "{nome} (Pokémon)" se existir.
"""

import logging
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlencode

from crawler.domain.exceptions import FetchError

if TYPE_CHECKING:
    from crawler.client import BulbapediaClient

OPENSEARCH_URL = "https://bulbapedia.bulbagarden.net/w/api.php"
POKEMON_SUFFIX = " (Pokémon)"

logger = logging.getLogger(__name__)


def find_pokemon_page(name: str, client: "BulbapediaClient") -> Optional[str]:
    """
    Usa o OpenSearch da Bulbapedia (via client compartilhado) e retorna a URL
    do artigo "{name} (Pokémon)" se existir; caso contrário None.
    """
    name = (name or "").strip()
    if not name:
        return None

    params = {
        "action": "opensearch",
        "format": "json",
        "formatversion": "2",
        "search": name,
        "namespace": "0",
        "limit": "10",
    }
    url = f"{OPENSEARCH_URL}?{urlencode(params)}"

    try:
        data = client.get_json_sync(url)
    except FetchError as e:
        logger.warning("Busca '%s' falhou: %s", name, e)
        return None

    if not isinstance(data, list) or len(data) < 4:
        return None

    titles = data[1] if isinstance(data[1], list) else []
    urls = data[3] if isinstance(data[3], list) else []
    if not titles or not urls:
        return None

    expected_title = f"{name}{POKEMON_SUFFIX}"
    try:
        idx = titles.index(expected_title)
        if idx < len(urls):
            return urls[idx]
    except ValueError:
        pass

    slug = name.replace(" ", "_")
    for u in urls:
        if isinstance(u, str) and f"{slug}_(Pok" in u:
            return u

    logger.debug("'%s': página '%s' não encontrada", name, expected_title)
    return None
