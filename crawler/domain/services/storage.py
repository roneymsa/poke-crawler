"""Serviço de domínio: armazenamento (exportação JSON e persistência em SQLite)."""

import json
import sqlite3
from pathlib import Path
from typing import List

from crawler.domain.models import AbilityInfo, BaseStats, Pokemon


class Storage:
    """Salva e carrega dados em JSON ou SQLite."""

    def __init__(self, db_path: str = "pokemon.db"):
        self.db_path = db_path

    def save_json(self, pokemons: List[Pokemon], path: str = "pokemon.json") -> None:
        """Exporta a lista de Pokémon para um arquivo JSON."""
        data = [p.model_dump(mode="json") for p in pokemons]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_json(self, path: str) -> List[Pokemon]:
        """Carrega uma lista de Pokémon a partir de um arquivo JSON."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [Pokemon.model_validate(item) for item in data]

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pokemon (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                national_dex_number INTEGER,
                category TEXT,
                types TEXT,
                hp INTEGER DEFAULT 0,
                attack INTEGER DEFAULT 0,
                defense INTEGER DEFAULT 0,
                sp_atk INTEGER DEFAULT 0,
                sp_def INTEGER DEFAULT 0,
                speed INTEGER DEFAULT 0,
                evolution_prev TEXT,
                evolution_next TEXT,
                abilities TEXT,
                image_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

    def save_sqlite(self, pokemons: List[Pokemon]) -> None:
        """Persiste a lista de Pokémon no SQLite."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            for p in pokemons:
                abilities_json = json.dumps([
                    {"name": a.name, "is_hidden": a.is_hidden}
                    for a in p.abilities
                ], ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO pokemon (
                        name, national_dex_number, category, types,
                        hp, attack, defense, sp_atk, sp_def, speed,
                        evolution_prev, evolution_next, abilities, image_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p.name,
                        p.national_dex_number,
                        p.category,
                        json.dumps(p.types, ensure_ascii=False),
                        p.base_stats.hp,
                        p.base_stats.attack,
                        p.base_stats.defense,
                        p.base_stats.sp_atk,
                        p.base_stats.sp_def,
                        p.base_stats.speed,
                        p.evolution_prev,
                        p.evolution_next,
                        abilities_json,
                        p.image_path,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def load_sqlite(self) -> List[Pokemon]:
        """Carrega todos os Pokémon do SQLite."""
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            rows = conn.execute("""
                SELECT name, national_dex_number, category, types,
                       hp, attack, defense, sp_atk, sp_def, speed,
                       evolution_prev, evolution_next, abilities, image_path
                FROM pokemon
            """).fetchall()
            result = []
            for row in rows:
                (name, ndex, category, types_json, hp, atk, defe, spa, spd, spe,
                 ev_prev, ev_next, abilities_json, image_path) = row
                types = json.loads(types_json) if types_json else []
                abilities = [
                    AbilityInfo(name=a["name"], is_hidden=a.get("is_hidden", False))
                    for a in json.loads(abilities_json or "[]")
                ]
                result.append(Pokemon(
                    name=name,
                    national_dex_number=ndex,
                    category=category,
                    types=types,
                    base_stats=BaseStats(hp=hp or 0, attack=atk or 0, defense=defe or 0,
                                        sp_atk=spa or 0, sp_def=spd or 0, speed=spe or 0),
                    evolution_prev=ev_prev,
                    evolution_next=ev_next,
                    abilities=abilities,
                    image_path=image_path,
                ))
            return result
        finally:
            conn.close()
