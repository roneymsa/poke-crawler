"""
Extrai links de Pokémon da página da National Pokédex da Bulbapedia.
Usado pela opção --get-all.
"""

from urllib.parse import urljoin, unquote

from lxml import html

LIST_PAGE_PATH = "/wiki/List_of_Pokémon_by_National_Pokédex_number"
XPATH_LINKS = '//tr[contains(@style,"background:#FFF")]//td[contains(@style,"font-family:monospace")]/following-sibling::td[1]/span/a'


def extract_pokemon_links(html_content: str, base_url: str = "https://bulbapedia.bulbagarden.net") -> list[tuple[str, str]]:
    """
    Extrai (nome, url) de todos os Pokémon na lista da National Pokédex.
    base_url é usado para transformar hrefs relativos em URLs absolutas.
    """
    base_url = base_url.rstrip("/")
    tree = html.fromstring(html_content)
    links = tree.xpath(XPATH_LINKS)
    result: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    for a in links:
        href = a.get("href")
        if not href or href.startswith("#"):
            continue
        url = urljoin(f"{base_url}/", href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        name = (a.text or "").strip() or unquote(href.split("/")[-1].replace("_", " ").split("(")[0].strip())
        if name:
            result.append((name, url))

    return result
