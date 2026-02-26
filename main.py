"""
Poké-Crawler: extrai dados de Pokémon da Bulbapedia.
Uso: python main.py [Bulbasaur] [Charmander] ...
Ou:  python main.py --list list.txt
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler.client import BulbapediaClient, FetchError

logger = logging.getLogger(__name__)
from crawler.parser import BulbapediaParser
from crawler.downloader import ImageDownloader
from crawler.storage import Storage
from crawler.models import Pokemon


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").replace("'", "%27")

async def fetch_one(
    client: BulbapediaClient,
    parser: BulbapediaParser,
    downloader: ImageDownloader,
    name: str,
) -> Pokemon | None:
    path = f"wiki/{_slug(name)}_(Pokémon)"
    logger.info("Processando Pokémon: %s (%s)", name, path)
    try:
        html = await client.get_page(path)
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
    names: list[str],
    output_json: str | None,
    output_db: str | None,
    images_dir: str,
    max_concurrency: int = 3,
) -> list[Pokemon]:
    """Requisita vários Pokémon em concorrência limitada e retorna a lista."""
    parser = BulbapediaParser()
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _bounded_fetch(
        client: BulbapediaClient,
        downloader: ImageDownloader,
        name: str,
    ) -> Pokemon | None:
        async with semaphore:
            return await fetch_one(client, parser, downloader, name)

    async def _run() -> list[Pokemon]:
        async with BulbapediaClient() as client:
            downloader = ImageDownloader(images_dir=images_dir, client=client)
            tasks = [_bounded_fetch(client, downloader, n) for n in names]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            return [p for p in results if p is not None]

    pokemons = await _run()
    storage = Storage(db_path=output_db or "pokemon.db")
    if output_json:
        storage.save_json(pokemons, output_json)
    if output_db or not output_json:
        storage.save_sqlite(pokemons)
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
    args = ap.parse_args()

    names = list(args.names)
    if args.list:
        p = Path(args.list)
        if p.exists():
            names.extend(p.read_text(encoding="utf-8").strip().splitlines())
    names = [n.strip() for n in names if n.strip()]
    if not names:
        logger.error("Informe nomes de Pokémon ou --list FILE.")
        sys.exit(1)
    output_json = None if args.no_json else args.json
    pokemons = asyncio.run(
        run_concurrent(
            names,
            output_json,
            args.db,
            args.images,
            max_concurrency=args.workers,
        )
    )
    logger.info("Extraídos: %d Pokémon.", len(pokemons))
    if output_json:
        logger.info("JSON: %s", output_json)
    logger.info("SQLite: %s", args.db or "pokemon.db")


if __name__ == "__main__":
    main()
