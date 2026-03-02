"""
Lógica de execução do crawler: fetch de um Pokémon, run concorrente, sync de links e worker.
"""

import asyncio
import logging
import random

from crawler import BulbapediaClient, FetchError, Pokemon, Storage
from crawler.client import BASE_URL
from crawler.parser import BulbapediaParser
from crawler.downloader import ImageDownloader
from crawler.search import find_pokemon_page
from crawler import national_dex

try:
    from config import BATCH_SIZE, DELAY_MIN, DELAY_MAX, MAX_RETRIES
except ImportError:
    BATCH_SIZE = 25
    DELAY_MIN = 2
    DELAY_MAX = 6
    MAX_RETRIES = 3

logger = logging.getLogger(__name__)


async def fetch_one(
    client: BulbapediaClient,
    parser: BulbapediaParser,
    downloader: ImageDownloader,
    name: str,
    page_url: str,
) -> Pokemon | None:
    """Busca, parseia e baixa imagens de um Pokémon; retorna None em falha."""
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
    paths = await parser.extract_and_download_form_images(html, pokemon, downloader)
    if paths:
        first_path = paths[0][1]
        form_paths = {k: v for k, v in paths if k} if len(paths) > 1 else None
        pokemon = pokemon.model_copy(
            update={"image_path": first_path, "form_image_paths": form_paths}
        )
    return pokemon


async def run_concurrent(
    names: list[str] | None = None,
    resolved: list[tuple[str, str]] | None = None,
    output_json: str | None = None,
    output_db: str | None = None,
    images_dir: str = "images",
    max_concurrency: int = 3,
    resolve_all_matches: bool = False,
) -> list[Pokemon]:
    """Requisita vários Pokémon em concorrência limitada e retorna a lista.
    Forneça names (para buscar por nome) ou resolved (lista de (nome, url))."""
    parser = BulbapediaParser()
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async with BulbapediaClient() as client:
        if resolved is None:
            resolved = []
            seen_urls: set[str] = set()

            def _add_resolved(display_name: str, page_url: str) -> None:
                if page_url in seen_urls:
                    return
                seen_urls.add(page_url)
                resolved.append((display_name, page_url))

            for n in names or []:
                matches = find_pokemon_page(n, client)
                if not matches:
                    logger.warning("'%s': não encontrado na Bulbapedia (será ignorado)", n)
                    continue

                if resolve_all_matches:
                    for display_name, page_url in matches:
                        _add_resolved(display_name, page_url)
                    continue

                chosen_name, chosen_url = matches[0]
                if len(matches) > 1:
                    others = ", ".join(m[0] for m in matches[1:])
                    logger.warning(
                        "'%s': múltiplas correspondências (%s). Usando '%s'. Use --all-matches para processar todas.",
                        n,
                        others,
                        chosen_name,
                    )
                _add_resolved(chosen_name, chosen_url)

        if not resolved:
            logger.warning("Nenhum Pokémon para processar.")
            return []

        db_path = output_db or "pokemon.db"
        storage = Storage(db_path=db_path)
        downloader = ImageDownloader(images_dir=images_dir, client=client)

        async def _bounded_fetch(name: str, page_url: str) -> Pokemon | None:
            async with semaphore:
                pokemon = await fetch_one(client, parser, downloader, name, page_url)
                if pokemon is not None:
                    storage.save_one_sqlite(pokemon)
                return pokemon

        tasks = [_bounded_fetch(n, url) for n, url in resolved]
        pokemons: list[Pokemon] = []
        for coro in asyncio.as_completed(tasks):
            p = await coro
            if p is not None:
                pokemons.append(p)

    if output_json:
        storage.export_json_from_db(output_json)
    return pokemons


async def run_sync_links(db_path: str) -> None:
    """Job 1: busca lista da National Dex e upserta (name, url, status=pending) no banco."""
    logger.info("Sync de links: iniciando (db=%s)", db_path)
    storage = Storage(db_path=db_path)
    async with BulbapediaClient() as client:
        html_list = await client.get_page(national_dex.LIST_PAGE_PATH)
    resolved = national_dex.extract_pokemon_links(html_list, BASE_URL)
    count = 0
    for name, url in resolved:
        storage.upsert_pokemon_link(name, url)
        count += 1
    logger.info("Sync de links: %d Pokémon upsertados.", count)


async def run_worker(
    db_path: str,
    images_dir: str = "images",
    batch_size: int = BATCH_SIZE,
) -> None:
    """Job 2: processa um lote de pendentes (fetch → parse → imagens → save), com delay anti-ban."""
    storage = Storage(db_path=db_path)
    batch = storage.get_pending_batch(limit=batch_size, max_retries=MAX_RETRIES)
    if not batch:
        logger.info("Worker: nada pendente.")
        return
    logger.info("Worker: processando lote de %d Pokémon.", len(batch))
    parser = BulbapediaParser()
    async with BulbapediaClient() as client:
        downloader = ImageDownloader(images_dir=images_dir, client=client)
        for pokemon_id, name, url, retries in batch:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            logger.info("Aguardando %.1fs (anti-ban)...", delay)
            await asyncio.sleep(delay)
            pokemon = await fetch_one(client, parser, downloader, name, url)
            if pokemon is not None:
                storage.save_one_sqlite(pokemon)
                logger.info("%s: ok (status=done).", name)
            else:
                retries += 1
                storage.mark_error(pokemon_id, retries, max_retries=MAX_RETRIES)
                logger.warning("%s: falha (retries=%d).", name, retries)
    logger.info("Worker: lote finalizado.")
