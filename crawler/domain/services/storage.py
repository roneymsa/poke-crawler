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
                form_image_paths TEXT,
                gender_ratio TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        for col, typ in [
            ("form_image_paths", "TEXT"),
            ("url", "TEXT"),
            ("status", "TEXT DEFAULT 'pending'"),
            ("retries", "INTEGER DEFAULT 0"),
            ("updated_at", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE pokemon ADD COLUMN {col} {typ}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
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
        form_image_paths_json = (
            json.dumps(p.form_image_paths, ensure_ascii=False) if p.form_image_paths else None
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
            form_image_paths_json,
            gender_ratio_json,
            p.name,
        )
        cur = conn.execute(
            """
            UPDATE pokemon SET
                national_dex_number = ?, category = ?, types = ?,
                hp = ?, attack = ?, defense = ?, sp_atk = ?, sp_def = ?, speed = ?,
                evolution_prev = ?, evolution_next = ?, abilities = ?, image_path = ?, form_image_paths = ?, gender_ratio = ?,
                status = 'done', updated_at = CURRENT_TIMESTAMP, retries = 0
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
                    evolution_prev, evolution_next, abilities, image_path, form_image_paths, gender_ratio,
                    status, retries
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'done', 0)
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
                    form_image_paths_json,
                    gender_ratio_json,
                ),
            )

    def save_one_sqlite(self, pokemon: Pokemon) -> None:
        """Persiste um único Pokémon no SQLite (upsert por nome). Atualiza status='done', updated_at, retries=0."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            self._upsert_one(conn, pokemon)
            conn.commit()
        finally:
            conn.close()

    def upsert_pokemon_link(self, name: str, url: str) -> None:
        """Insere ou atualiza (name, url) e define status='pending', retries=0. Usado pelo job de sync."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            cur = conn.execute(
                "UPDATE pokemon SET url = ?, status = 'pending', retries = 0 WHERE name = ?",
                (url, name),
            )
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT INTO pokemon (name, url, status, retries) VALUES (?, ?, 'pending', 0)",
                    (name, url),
                )
            conn.commit()
        finally:
            conn.close()

    def get_pending_batch(
        self, limit: int, max_retries: int = 3
    ) -> list[tuple[int, str, str, int]]:
        """
        Retorna lote de pendentes: (id, name, url, retries).
        status IN ('pending','failed'), retries < max_retries, ordenado por updated_at ASC NULLS FIRST.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT id, name, url, COALESCE(retries, 0)
                FROM pokemon
                WHERE (status = 'pending' OR status = 'failed')
                  AND (retries IS NULL OR retries < ?)
                  AND url IS NOT NULL AND url != ''
                ORDER BY updated_at ASC NULLS FIRST, id ASC
                LIMIT ?
                """,
                (max_retries, limit),
            ).fetchall()
            return [(r[0], r[1], r[2], r[3]) for r in rows]
        finally:
            conn.close()

    def mark_error(self, pokemon_id: int, retries: int, max_retries: int = 3) -> None:
        """Marca falha: incrementa retries; status='failed' se retries >= max_retries."""
        status = "failed" if retries >= max_retries else "pending"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE pokemon SET status = ?, retries = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, retries, pokemon_id),
            )
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

    def export_json_from_db(
        self, path: str = "pokemon.json", only_done: bool = False
    ) -> None:
        """Exporta para JSON os Pokémon do SQLite. Se only_done=True, só os com status='done'."""
        pokemons = self.load_sqlite(only_done=only_done)
        self.save_json(pokemons, path)

    def load_sqlite(self, only_done: bool = False) -> List[Pokemon]:
        """Carrega Pokémon do SQLite. Se only_done=True, apenas os com status='done'."""
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_schema(conn)
            where = " WHERE status = 'done'" if only_done else ""
            rows = conn.execute(
                """
                SELECT name, national_dex_number, category, types,
                       hp, attack, defense, sp_atk, sp_def, speed,
                       evolution_prev, evolution_next, abilities, image_path, form_image_paths, gender_ratio
                FROM pokemon
                """
                + where
            ).fetchall()
            result = []
            for row in rows:
                (name, ndex, category, types_json, hp, atk, defe, spa, spd, spe,
                 ev_prev, ev_next, abilities_json, image_path, form_image_paths_json, gender_ratio) = row
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
                form_image_paths = None
                if form_image_paths_json:
                    try:
                        form_image_paths = json.loads(form_image_paths_json)
                    except (json.JSONDecodeError, TypeError):
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
                    form_image_paths=form_image_paths,
                    gender_ratio=gender_ratio_obj,
                ))
            return result
        finally:
            conn.close()
