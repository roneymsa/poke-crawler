"""
Exporta SELECT * FROM pokemon do SQLite para CSV.
Uso: py export_pokemon_csv.py [--db todos_pokemons.db] [--out todos_pokemons.csv]
"""
import argparse
import csv
import sqlite3
from pathlib import Path

# Diretório do script = raiz do projeto (para defaults relativos a ele)
SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description="Exportar tabela pokemon do SQLite para CSV")
    ap.add_argument("--db", default="todos_pokemons.db", help="Caminho do SQLite (default: todos_pokemons.db)")
    ap.add_argument("--out", "-o", default="todos_pokemons.csv", help="Arquivo CSV de saída (default: todos_pokemons.csv)")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = SCRIPT_DIR / args.db
    if not db_path.exists():
        print(f"Erro: arquivo não encontrado: {db_path}")
        print("Execute o crawler (--all) primeiro para criar todos_pokemons.db")
        return

    conn = sqlite3.connect(str(db_path))
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pokemon'"
    ).fetchone()
    if not has_table:
        print("Erro: tabela 'pokemon' não existe neste banco.")
        print("Execute o crawler (--all) primeiro para popular todos_pokemons.db")
        conn.close()
        return

    cur = conn.execute("SELECT * FROM pokemon")
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description]

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    conn.close()
    print(f"Exportados {len(rows)} registros para {args.out}")


if __name__ == "__main__":
    main()
