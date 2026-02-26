"""Parsing do HTML da Bulbapedia com BeautifulSoup."""

import re
from typing import Optional
from bs4 import BeautifulSoup

from crawler.domain.models import AbilityInfo, BaseStats, Pokemon

BULBAPEDIA_IMAGE_BASE = "https://bulbapedia.bulbagarden.net"

def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    s = (value or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None

def _normalize_type(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s*\([^)]*\)\s*", "", s)
    return s.strip() or ""


def _td_is_visible(td) -> bool:
    """True se o td não está oculto por display:none."""
    style = (td.get("style") or "").replace(" ", "").lower()
    return "display:none" not in style


def _is_valid_ability_name(name: str) -> bool:
    """Filtra rótulos que não são nomes de habilidade."""
    return bool(name) and name.lower() not in {
        "ability",
        "abilities",
        "hidden ability",
    }


def _full_image_url(src: str) -> str:
    """Converte src de imagem (relativo ou absoluto) em URL absoluta."""
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("http"):
        return src
    return BULBAPEDIA_IMAGE_BASE + src


def _dedupe_abilities(abilities: list[AbilityInfo]) -> list[AbilityInfo]:
    """Remove duplicatas por (name, is_hidden) mantendo a ordem."""
    seen: set[tuple[str, bool]] = set()
    out: list[AbilityInfo] = []
    for a in abilities:
        key = (a.name, a.is_hidden)
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


STAT_MAP = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "sp atk": "sp_atk",
    "sp. atk": "sp_atk",
    "sp def": "sp_def",
    "sp. def": "sp_def",
    "speed": "speed",
}

class BulbapediaParser:
    def parse(self, html: str, page_name: Optional[str] = None) -> Pokemon:
        soup = BeautifulSoup(html, "html.parser")

        name = self._extract_name(soup, page_name)
        national_dex_number = self._extract_national_dex(soup)
        category = self._extract_category(soup)
        types = self._extract_types(soup)
        base_stats = self._extract_base_stats(soup)
        abilities = self._extract_abilities(soup)
        evolution_prev, evolution_next = self._extract_evolutions(
            soup, current_name=name
        )

        return Pokemon(
            name=name,
            national_dex_number=national_dex_number,
            category=category,
            types=types,
            base_stats=base_stats,
            evolution_prev=evolution_prev or None,
            evolution_next=evolution_next or None,
            abilities=abilities,
            image_path=None,
        )

    def get_image_url(self, html: str, pokemon_name: Optional[str] = None) -> Optional[str]:
        """Extrai a URL da imagem principal do Pokémon a partir do HTML."""
        soup = BeautifulSoup(html, "html.parser")
        return self._extract_image_url(soup, pokemon_name=pokemon_name)

    def _extract_name(self, soup: BeautifulSoup, page_name: Optional[str]) -> str:
        first_heading = soup.find("h1", id="firstHeading")
        if not first_heading:
            return ""
        text = first_heading.get_text(strip=True)
        return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()

    def _find_infobox_tables(self, soup: BeautifulSoup):
        return soup.find_all(
            "table",
            class_=re.compile(r"roundy|infobox", re.I),
        )

    def _dex_from_infobox_row(self, row) -> Optional[int]:
        """Extrai o número do National Dex de uma linha (tr) da infobox, se existir."""
        cells = row.find_all(["th", "td"])
        for i, cell in enumerate(cells):
            text = cell.get_text(strip=True)
            match = re.search(r"#?\s*(\d{3,4})\s*$", text)
            if match:
                return _safe_int(match.group(1))
            if (
                "national" in text.lower()
                and "dex" in text.lower()
                and i + 1 < len(cells)
            ):
                return _safe_int(cells[i + 1].get_text(strip=True))
        return None

    def _find_dex_in_infobox(self, soup: BeautifulSoup) -> Optional[int]:
        for table in self._find_infobox_tables(soup):
            for row in table.find_all("tr"):
                dex = self._dex_from_infobox_row(row)
                if dex is not None:
                    return dex
        return None

    def _extract_national_dex(self, soup: BeautifulSoup) -> Optional[int]:
        return self._find_dex_in_infobox(soup)

    def _extract_category(self, soup: BeautifulSoup) -> Optional[str]:
        a = soup.find("a", title="Pokémon category")
        if not a:
            return None
        return a.get_text(strip=True) or None

    def _extract_types(self, soup: BeautifulSoup) -> list[str]:
        types: list[str] = []
        type_link = soup.find("a", title="Type")
        if not type_link:
            return []
        section_td = type_link.find_parent("td")
        if not section_td:
            return []
        style_hidden = "display:none"
        for td in section_td.find_all("td"):
            style = (td.get("style") or "").replace(" ", "").lower()
            if style_hidden in style:
                continue
            for a in td.find_all("a", href=re.compile(r"\(type\)", re.I)):
                span = a.find("span")
                b = span.find("b") if span else None
                name = (b.get_text(strip=True) if b else a.get_text(strip=True))
                if not name:
                    continue
                t = _normalize_type(name)
                if t and t not in types and t.lower() != "unknown":
                    types.append(t)
        return types[:2]

    def _extract_base_stats(self, soup: BeautifulSoup) -> BaseStats:
        """
        Extrai base stats da seção Base stats: span#Base_stats → h4 → próxima tabela.
        Em cada tr, th com 2 divs (recursive=False): primeiro = nome do stat, segundo = valor.
        """
        stats: dict[str, int] = {}

        span = soup.find("span", id="Base_stats")
        if not span:
            return self._base_stats_from_map(stats)

        h4 = span.find_parent("h4")
        if not h4:
            return self._base_stats_from_map(stats)

        table = h4.find_next("table")
        if not table:
            return self._base_stats_from_map(stats)

        for row in table.find_all("tr"):
            th = row.find("th")
            if not th:
                continue

            divs = th.find_all("div", recursive=False)
            if len(divs) != 2:
                continue

            stat_name = divs[0].get_text(strip=True).replace(":", "").lower()
            stat_value = divs[1].get_text(strip=True)

            key = STAT_MAP.get(stat_name)
            if not key:
                continue

            val = _safe_int(stat_value)
            if val is not None and 0 <= val <= 255:
                stats[key] = val

            if len(stats) == 6:
                break

        return self._base_stats_from_map(stats)

    def _base_stats_from_map(self, stats: dict[str, int]) -> BaseStats:
        """Monta BaseStats a partir do dicionário (usa 0 para chaves ausentes)."""
        return BaseStats(
            hp=stats.get("hp", 0),
            attack=stats.get("attack", 0),
            defense=stats.get("defense", 0),
            sp_atk=stats.get("sp_atk", 0),
            sp_def=stats.get("sp_def", 0),
            speed=stats.get("speed", 0),
        )

    def _find_evolution_div(self, soup: BeautifulSoup):
        """Retorna a div da seção Evolution (primeiro irmão div do h3#Evolution) ou None."""
        evolution_span = soup.find("span", id="Evolution")
        if not evolution_span:
            return None
        h3 = evolution_span.find_parent("h3")
        if not h3:
            return None
        return h3.find_next_sibling("div")

    def _evolution_table_has_stage_and_link(self, table) -> bool:
        """True se a tabela tem stage (Unevolved/First Evolution/...) e link de Pokémon."""
        link_re = re.compile(r"_\(Pok", re.I)
        stage_re = re.compile(
            r"^(Unevolved|First Evolution|Second Evolution)$", re.I
        )
        has_link = table.find("a", href=link_re) or table.find(
            "a", class_=re.compile(r"selflink", re.I)
        )
        if not has_link:
            return False
        return any(
            stage_re.match(s.get_text(strip=True))
            for s in table.find_all("small")
        )

    def _extract_evolution_chain(self, evolution_div) -> list[str]:
        """
        Extrai a linha evolutiva (nomes na ordem) a partir da div da seção Evolution.
        Ordem pelas tabelas (slots), não pela ordem dos links no DOM.
        Suporta múltiplas evoluções e formas (ex. Raichu (Alolan)).
        """
        if not evolution_div:
            return []
        chain: list[str] = []
        link_re = re.compile(r"_\(Pok", re.I)
        stage_re = re.compile(
            r"^(Unevolved|First Evolution|Second Evolution)$", re.I
        )

        for table in evolution_div.find_all("table"):
            if not self._evolution_table_has_stage_and_link(table):
                continue
            if any(
                self._evolution_table_has_stage_and_link(t)
                for t in table.find_all("table")
            ):
                continue
            stage_small = None
            for s in table.find_all("small"):
                if stage_re.match(s.get_text(strip=True)):
                    stage_small = s
                    break
            if not stage_small:
                continue
            a = table.find("a", href=link_re) or table.find(
                "a", class_=re.compile(r"selflink", re.I)
            )
            if not a:
                continue
            name = a.get_text(strip=True)
            if not name or name in ("→", "←", "↗", "↘"):
                continue
            for form_s in table.find_all("small"):
                if form_s is stage_small:
                    continue
                form_text = form_s.get_text(strip=True)
                if form_text and "Form" in form_text:
                    form_name = form_text.replace(" Form", "").strip()
                    if form_name:
                        name = f"{name} ({form_name})"
                    break
            chain.append(name)
        return chain

    def _resolve_prev_next(
        self, chain: list[str], current_name: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """Dada a cadeia evolutiva e o nome do Pokémon atual, retorna (prev, next)."""
        if not chain:
            return (None, None)
        prev_name: Optional[str] = None
        next_name: Optional[str] = None
        idx: Optional[int] = None
        if current_name:
            current_lower = current_name.lower()
            for i, n in enumerate(chain):
                base = n.split(" (")[0].strip().lower()
                if base == current_lower or n.lower() == current_lower:
                    idx = i
                    break
        if idx is None:
            next_name = chain[0] if chain else None
            return (prev_name, next_name)
        if idx > 0:
            prev_name = chain[idx - 1]
        if idx + 1 < len(chain):
            next_name = chain[idx + 1]  # apenas a primeira evolução seguinte
        return (prev_name, next_name)

    def _extract_evolutions(
        self, soup: BeautifulSoup, current_name: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        div = self._find_evolution_div(soup)
        chain = self._extract_evolution_chain(div) if div else []
        return self._resolve_prev_next(chain, current_name)

    def _extract_abilities_from_td(self, td) -> list[AbilityInfo]:
        """Extrai habilidades de um único <td> (pode retornar várias)."""
        if not _td_is_visible(td):
            return []
        text = td.get_text(" ", strip=True)
        if not text:
            return []
        hidden = "hidden ability" in text.lower()
        result: list[AbilityInfo] = []
        links = td.find_all("a")
        if links:
            for a in links:
                name = a.get_text(strip=True)
                if _is_valid_ability_name(name):
                    result.append(AbilityInfo(name=name, is_hidden=hidden))
        else:
            for part in re.split(r"[,/]", text):
                part = part.strip()
                if _is_valid_ability_name(part) and "hidden" not in part.lower():
                    result.append(AbilityInfo(name=part, is_hidden=False))
        return result

    def _find_abilities_by_infobox_header(self, soup: BeautifulSoup) -> list[AbilityInfo]:
        """Busca habilidades na infobox pela linha com header 'ability'."""
        for table in self._find_infobox_tables(soup):
            for row in table.find_all("tr"):
                th = row.find("th")
                if not th or "ability" not in th.get_text(strip=True).lower():
                    continue
                abilities: list[AbilityInfo] = []
                for td in row.find_all("td"):
                    abilities.extend(self._extract_abilities_from_td(td))
                if abilities:
                    return abilities
        return []

    def _find_abilities_by_next_table(self, soup: BeautifulSoup) -> list[AbilityInfo]:
        """Busca habilidades na tabela seguinte a uma célula com 'abilities'."""
        for cell in soup.find_all(["th", "td"]):
            if "abilities" not in cell.get_text(strip=True).lower():
                continue
            table = cell.find_next(
                "table", class_=re.compile(r"roundy|infobox", re.I)
            )
            if not table:
                continue
            abilities: list[AbilityInfo] = []
            for td in table.find_all("td"):
                abilities.extend(self._extract_abilities_from_td(td))
            if abilities:
                return abilities
        return []

    def _extract_abilities(self, soup: BeautifulSoup) -> list[AbilityInfo]:
        """Extrai habilidades tentando infobox por header e depois por próxima tabela."""
        for finder in (
            self._find_abilities_by_infobox_header,
            self._find_abilities_by_next_table,
        ):
            abilities = finder(soup)
            if abilities:
                return _dedupe_abilities(abilities)
        return []

    def _extract_image_url(self, soup: BeautifulSoup, pokemon_name: Optional[str] = None) -> Optional[str]:
        name_norm = pokemon_name.lower() if pokemon_name else None
        if not name_norm:
            return None
        for table in self._find_infobox_tables(soup):
            for img in table.find_all("img"):
                src = img.get("src") or ""
                if not src:
                    continue
                alt = (img.get("alt") or "").lower()
                title = (img.get("title") or "").lower()
                parent = img.find_parent("a")
                parent_title = (parent.get("title") or "").lower() if parent else ""
                text_blob = " ".join([alt, title, parent_title])
                if name_norm not in text_blob:
                    continue
                if not re.search(r"(archives|bulbagarden)", src, re.I):
                    continue
                return _full_image_url(src)
        return None