"""Serviço de domínio: armazenamento (exportação JSON e persistência em SQLite)."""

import json
import sqlite3
from pathlib import Path
from typing import List

from crawler.domain.models import AbilityInfo, BaseStats, GenderRatio, Pokemon


def _deduplicate_by_name(pokemons: List[Pokemon]) -> List[Pokemon]:
    """Remove duplicatas pela referência forte (nome canônico). Mantém a última ocorrência."""
    by_name: dict[str, Pokemon] = {}
    for p in pokemons:
        if p.name:
            by_name[p.name] = p
    return list(by_name.values())


class Storage:
    """Salva e carrega dados em JSON ou SQLite."""

    def __init__(self, db_path: str = "pokemon.db"):
        self.db_path = db_path

    def save_json(self, pokemons: List[Pokemon], path: str = "pokemon.json") -> None:
        """Exporta a lista de Pokémon para um arquivo JSON (um por nome canônico)."""
        pokemons = _deduplicate_by_name(pokemons)
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
                name TEXT NOT NULL UNIQUE,
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
                gender_ratio TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

    def _upsert_one(self, conn: sqlite3.Connection, p: Pokemon) -> None:
        """Faz upsert de um único Pokémon na conexão já aberta."""
        abilities_json = json.dumps(
            [{"name": a.name, "is_hidden": a.is_hidden} for a in p.abilities],
            ensure_ascii=False,
        )
        gender_ratio_json = (
            json.dumps(p.gender_ratio.model_dump(mode="json"), ensure_ascii=False)
            if p.gender_ratio else None
        )
        row = (
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
            gender_ratio_json,
            p.name,
        )
        cur = conn.execute(
            """
            UPDATE pokemon SET
                national_dex_number = ?, category = ?, types = ?,
                hp = ?, attack = ?, defense = ?, sp_atk = ?, sp_def = ?, speed = ?,
                evolution_prev = ?, evolution_next = ?, abilities = ?, image_path = ?, gender_ratio = ?
            WHERE name = ?
            """,
            row,
        )
        if cur.rowcount == 0:
            conn.execute(
                """
                INSERT INTO pokemon (
                    name, national_dex_number, category, types,
                    hp, attack, defense, sp_atk, sp_def, speed,
                    evolution_prev, evolution_next, abilities, image_path, gender_ratio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    gender_ratio_json,
                ),
            )

    def save_one_sqlite(self, pokemon: Pokemon) -> None:
        """Persiste um único Pokémon no SQLite (upsert por nome). Chamado a cada parse."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            self._upsert_one(conn, pokemon)
            conn.commit()
        finally:
            conn.close()

    def save_sqlite(self, pokemons: List[Pokemon]) -> None:
        """Persiste a lista de Pokémon no SQLite (upsert por nome canônico)."""
        pokemons = _deduplicate_by_name(pokemons)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            for p in pokemons:
                self._upsert_one(conn, p)
            conn.commit()
        finally:
            conn.close()

    def export_json_from_db(self, path: str = "pokemon.json") -> None:
        """Exporta para JSON os Pokémon que estão no SQLite (busca os nomes salvos no banco)."""
        pokemons = self.load_sqlite()
        self.save_json(pokemons, path)

    def load_sqlite(self) -> List[Pokemon]:
        """Carrega todos os Pokémon do SQLite."""
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            rows = conn.execute("""
                SELECT name, national_dex_number, category, types,
                       hp, attack, defense, sp_atk, sp_def, speed,
                       evolution_prev, evolution_next, abilities, image_path, gender_ratio
                FROM pokemon
            """).fetchall()
            result = []
            for row in rows:
                (name, ndex, category, types_json, hp, atk, defe, spa, spd, spe,
                 ev_prev, ev_next, abilities_json, image_path, gender_ratio) = row
                types = json.loads(types_json) if types_json else []
                abilities = [
                    AbilityInfo(name=a["name"], is_hidden=a.get("is_hidden", False))
                    for a in json.loads(abilities_json or "[]")
                ]
                gender_ratio_obj = None
                if gender_ratio:
                    try:
                        data = json.loads(gender_ratio)
                        if data is not None:
                            gender_ratio_obj = GenderRatio.model_validate(data)
                    except (json.JSONDecodeError, ValueError):
                        pass
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
                    gender_ratio=gender_ratio_obj,
                ))
            return result
        finally:
            conn.close()
