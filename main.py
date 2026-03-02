"""
Poké-Crawler: extrai dados de Pokémon da Bulbapedia.
Uso: python main.py [Bulbasaur] [Charmander] ...
Ou:  python main.py --list list.txt
Ou:  python main.py --get-all  (todos da National Pokédex)
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler import BulbapediaClient, FetchError, Pokemon, Storage
from crawler.parser import BulbapediaParser
from crawler.downloader import ImageDownloader
from crawler.search import find_pokemon_page
from crawler import national_dex

logger = logging.getLogger(__name__)

def _unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


async def fetch_one(
    client: BulbapediaClient,
    parser: BulbapediaParser,
    downloader: ImageDownloader,
    name: str,
    page_url: str,
) -> Pokemon | None:
    logger.info("Processando Pokémon: %s (%s)", name, page_url)
    try:
        html = await client.get_page(page_url)
    except FetchError as e:
        if e.status_code == 404:
            logger.error("%s: Pokémon não encontrado", name)
        else:
            logger.error("%s: falha na requisição: %s", name, e)
        return None
    except Exception as e:
        logger.error("%s: falha na requisição: %s", name, e)
        return None
    try:
        pokemon = parser.parse(html, page_name=name)
    except Exception as e:
        logger.error("%s: falha no parsing: %s", name, e)
        return None
    image_url = parser.get_image_url(html, pokemon.name)
    if image_url:
        img_path = await downloader.download_async(image_url, pokemon)
        if img_path:
            pokemon = pokemon.model_copy(update={"image_path": img_path})
    return pokemon

async def run_concurrent(
    names: list[str] | None = None,
    resolved: list[tuple[str, str]] | None = None,
    output_json: str | None = None,
    output_db: str | None = None,
    images_dir: str = "images",
    max_concurrency: int = 3,
) -> list[Pokemon]:
    """Requisita vários Pokémon em concorrência limitada e retorna a lista.
    Forneça names (para buscar por nome) ou resolved (lista de (nome, url))."""
    parser = BulbapediaParser()
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async with BulbapediaClient() as client:
        if resolved is None:
            resolved = []
            for n in names or []:
                page_url = find_pokemon_page(n, client)
                if page_url:
                    resolved.append((n, page_url))
                else:
                    logger.warning("'%s': não encontrado na Bulbapedia (será ignorado)", n)

        if not resolved:
            logger.warning("Nenhum Pokémon para processar.")
            return []

        db_path = output_db or "pokemon.db"
        storage = Storage(db_path=db_path)

        async def _bounded_fetch(name: str, page_url: str) -> Pokemon | None:
            async with semaphore:
                pokemon = await fetch_one(client, parser, downloader, name, page_url)
                if pokemon is not None:
                    storage.save_one_sqlite(pokemon)
                return pokemon

        downloader = ImageDownloader(images_dir=images_dir, client=client)
        tasks = [_bounded_fetch(n, url) for n, url in resolved]
        pokemons: list[Pokemon] = []
        for coro in asyncio.as_completed(tasks):
            p = await coro
            if p is not None:
                pokemons.append(p)

    if output_json:
        storage.export_json_from_db(output_json)
    return pokemons


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
    )
    ap = argparse.ArgumentParser(description="Poké-Crawler (Bulbapedia)")
    ap.add_argument("names", nargs="*", help="Nomes dos Pokémon (ex: Bulbasaur Charmander)")
    ap.add_argument("--list", "-l", metavar="FILE", help="Arquivo com um nome por linha")
    ap.add_argument("--json", "-j", metavar="FILE", default="pokemon.json", help="Salvar JSON (default: pokemon.json)")
    ap.add_argument("--db", metavar="FILE", help="Salvar SQLite (default: pokemon.db)")
    ap.add_argument("--images", "-i", default="images", help="Pasta de imagens (default: images)")
    ap.add_argument(
        "--workers",
        "-w",
        type=int,
        default=3,
        help="Número máximo de pokémons sendo buscados em paralelo (default: 3)",
    )
    ap.add_argument("--no-json", action="store_true", help="Não salvar JSON")
    ap.add_argument(
        "--get-all",
        action="store_true",
        help="Extrair todos os Pokémon da National Pokédex (salva em todos_pokemons.json / todos_pokemons.db, máx. 5 em paralelo)",
    )
    args = ap.parse_args()

    if args.get_all:
        async def _run_get_all() -> list[Pokemon]:
            async with BulbapediaClient() as client:
                logger.info("Baixando lista da National Pokédex...")
                html_list = await client.get_page(national_dex.LIST_PAGE_PATH)
                resolved = national_dex.extract_pokemon_links(html_list, client.base_url)
                logger.info("Encontrados %d Pokémon na lista.", len(resolved))
            return await run_concurrent(
                resolved=resolved,
                output_json="todos_pokemons.json",
                output_db="todos_pokemons.db",
                images_dir=args.images,
                max_concurrency=5,
            )

        pokemons = asyncio.run(_run_get_all())
        logger.info("Extraídos: %d Pokémon.", len(pokemons))
        logger.info("JSON: todos_pokemons.json")
        logger.info("SQLite: todos_pokemons.db")
        return

    names = list(args.names)
    if args.list:
        p = Path(args.list)
        if p.exists():
            names.extend(p.read_text(encoding="utf-8").strip().splitlines())
    names = [n.strip() for n in names if n.strip()]
    names = _unique_names(names)
    if not names:
        logger.error("Informe nomes de Pokémon, --list FILE ou --get-all.")
        sys.exit(1)
    output_json = None if args.no_json else args.json
    pokemons = asyncio.run(
        run_concurrent(
            names=names,
            output_json=output_json,
            output_db=args.db,
            images_dir=args.images,
            max_concurrency=args.workers,
        )
    )
    logger.info("Extraídos: %d Pokémon.", len(pokemons))
    if output_json:
        logger.info("JSON: %s", output_json)
    logger.info("SQLite: %s", args.db or "pokemon.db")


if __name__ == "__main__":
    main()
