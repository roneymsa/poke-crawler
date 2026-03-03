"""
CLI do Poké-Crawler: argumentos, parsing de nomes e dispatch para os runners.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from crawler import BulbapediaClient
from crawler import national_dex
from crawler.runners import run_concurrent, run_sync_links, run_worker

try:
    from config import BATCH_SIZE
except ImportError:
    BATCH_SIZE = 25

logger = logging.getLogger(__name__)


def _unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def _split_names_arg(value: str) -> list[str]:
    """Quebra lista passada em um único argumento (CSV/; ou linhas)."""
    if not value:
        return []
    parts = value.replace(";", ",").replace("\n", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


def _read_names_file(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    lines = p.read_text(encoding="utf-8").splitlines()
    names: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Poké-Crawler (Bulbapedia)")
    ap.add_argument(
        "positional_names",
        nargs="*",
        metavar="NOME",
        help='Nomes dos Pokémon (ex: Bulbasaur Charmander). Dica: use aspas para nomes com espaço, ex: "Mr. Mime"',
    )
    ap.add_argument(
        "--name",
        action="append",
        default=[],
        help='Adicionar um nome (pode repetir). Ex: --name "Mr. Mime" --name Pikachu',
    )
    ap.add_argument(
        "--names",
        metavar="LIST",
        help='Lista em um único argumento (separada por vírgula/;). Ex: --names "Mr. Mime, Pikachu"',
    )
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
        "--all-matches",
        action="store_true",
        help="Quando um nome tiver múltiplas correspondências na busca, processar todas (padrão: usar só a primeira)",
    )
    ap.add_argument(
        "--get-all",
        action="store_true",
        help="Extrair todos os Pokémon da National Pokédex (salva em todos_pokemons.json / todos_pokemons.db, máx. 5 em paralelo)",
    )
    ap.add_argument(
        "--sync-links",
        action="store_true",
        help="Cron diário: busca a lista da National Dex e upserta (name, url, status=pending) no banco.",
    )
    ap.add_argument(
        "--worker",
        action="store_true",
        help="Cron frequente: processa um lote de pendentes (fetch + parse + imagens + save), com delay anti-ban.",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help="Tamanho do lote no --worker (default: %s)" % BATCH_SIZE,
    )
    return ap


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
    )
    ap = _build_parser()
    args = ap.parse_args()

    if args.sync_links:
        asyncio.run(run_sync_links(db_path=args.db or "todos_pokemons.db"))
        return

    if args.worker:
        asyncio.run(
            run_worker(
                db_path=args.db or "todos_pokemons.db",
                images_dir=args.images,
                batch_size=args.batch_size,
            )
        )
        return

    if args.get_all:
        async def _run_get_all():
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
        logger.info("Imagens: %s", args.images)
        return

    names: list[str] = []
    names.extend(args.positional_names or [])
    names.extend(args.name or [])
    if args.names is not None and isinstance(args.names, str):
        names.extend(_split_names_arg(args.names))
    if args.list:
        try:
            names.extend(_read_names_file(args.list))
        except FileNotFoundError:
            logger.error("Arquivo não encontrado: %s", args.list)
            sys.exit(2)
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
            resolve_all_matches=args.all_matches,
        )
    )
    logger.info("Extraídos: %d Pokémon.", len(pokemons))
    if output_json:
        logger.info("JSON: %s", output_json)
    logger.info("SQLite: %s", args.db or "pokemon.db")
    logger.info("Imagens: %s", args.images)


if __name__ == "__main__":
    main()
