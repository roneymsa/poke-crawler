"""
Resolução de nomes de Pokémon via API OpenSearch da Bulbapedia.
Retorna lista de (nome_exibição, url) para páginas "{nome} (Pokémon)".
Ex.: "Nidoran" pode retornar [("Nidoran♂", url_m), ("Nidoran♀", url_f)].
"""

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from crawler.domain.exceptions import FetchError

if TYPE_CHECKING:
    from crawler.client import BulbapediaClient

OPENSEARCH_URL = "https://bulbapedia.bulbagarden.net/w/api.php"
POKEMON_SUFFIX = " (Pokémon)"

logger = logging.getLogger(__name__)

def find_pokemon_page(name: str, client: "BulbapediaClient") -> list[tuple[str, str]]:
    """
    Usa o OpenSearch da Bulbapedia e retorna lista de (nome_exibição, url) para
    artigos que batem com "{name} (Pokémon)" (inclui variantes Nidoran♂/Nidoran♀).
    """
    name = (name or "").strip()
    if not name:
        return []

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
        return []

    if not isinstance(data, list) or len(data) < 4:
        return []

    titles = data[1] if isinstance(data[1], list) else []
    urls = data[3] if isinstance(data[3], list) else []
    if not titles or not urls:
        return []

    # Match exato: "Name (Pokémon)"
    expected_title = f"{name}{POKEMON_SUFFIX}"
    try:
        idx = titles.index(expected_title)
        if idx < len(urls) and isinstance(urls[idx], str):
            return [(name, urls[idx])]
    except ValueError:
        pass

    # Títulos "(Pokémon)" cujo nome começa com a busca (ex.: "Lucari" → "Lucario (Pokémon)", "Nidoran" → Nidoran♂/♀)
    results: list[tuple[str, str]] = []
    for i, title in enumerate(titles):
        if not isinstance(title, str) or not title.endswith(POKEMON_SUFFIX):
            continue
        prefix = title[: -len(POKEMON_SUFFIX)].strip()
        if (prefix == name or prefix.startswith(name)) and i < len(urls) and isinstance(urls[i], str):
            results.append((prefix, urls[i]))
    if results:
        return results

    # Fallback: slug na URL (ex.: Nidoran_(Pokémon))
    slug = name.replace(" ", "_")
    for i, u in enumerate(urls):
        if isinstance(u, str) and f"{slug}_(Pok" in u and i < len(titles) and POKEMON_SUFFIX in str(titles[i]):
            return [(name, u)]

    logger.debug("'%s': página '%s' não encontrada", name, expected_title)
    return []
