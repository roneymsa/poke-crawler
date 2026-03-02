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
    A API é case-insensitive (ex.: "beldum" já retorna "Beldum (Pokémon)"); o matching
    interno também ignora maiúsculas/minúsculas.
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

    # Match exato (case-insensitive): "beldum" → "Beldum (Pokémon)" retornado pela API
    name_lower = name.lower()
    expected_suffix = (name + POKEMON_SUFFIX).lower()
    for i, title in enumerate(titles):
        if not isinstance(title, str) or not title.endswith(POKEMON_SUFFIX):
            continue
        if title.lower() == expected_suffix and i < len(urls) and isinstance(urls[i], str):
            prefix = title[: -len(POKEMON_SUFFIX)].strip()
            return [(prefix, urls[i])]

    # Títulos "(Pokémon)" cujo nome começa com a busca (ex.: "Lucari" → "Lucario", "Nidoran" → Nidoran♂/♀)
    results: list[tuple[str, str]] = []
    for i, title in enumerate(titles):
        if not isinstance(title, str) or not title.endswith(POKEMON_SUFFIX):
            continue
        prefix = title[: -len(POKEMON_SUFFIX)].strip()
        if (prefix.lower() == name_lower or prefix.lower().startswith(name_lower)) and i < len(urls) and isinstance(urls[i], str):
            results.append((prefix, urls[i]))
    if results:
        return results

    # Fallback: slug na URL (case-insensitive)
    slug = name.replace(" ", "_").lower()
    for i, u in enumerate(urls):
        if isinstance(u, str) and slug in u.lower() and "_(pok" in u.lower() and i < len(titles) and POKEMON_SUFFIX in str(titles[i]):
            prefix = titles[i][: -len(POKEMON_SUFFIX)].strip() if isinstance(titles[i], str) else name
            return [(prefix, u)]

    logger.debug("'%s': página '(Pokémon)' não encontrada", name)
    return []
