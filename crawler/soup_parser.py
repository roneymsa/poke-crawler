"""
Parsing do HTML da Bulbapedia com BeautifulSoup.

Este parser espelha a API do `crawler.parser.BulbapediaParser`:
- parse()
- get_image_url()
- get_image_specs()
- extract_and_download_form_images()
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from bs4 import BeautifulSoup

from crawler.domain.models import AbilityInfo, BaseStats, GenderRatio, Pokemon

if TYPE_CHECKING:
    from crawler.downloader import ImageDownloader


BULBAPEDIA_IMAGE_BASE = "https://bulbapedia.bulbagarden.net"
MIN_FORMS_FOR_MULTI_IMAGE = 2
MIN_ARTWORK_PX = 100


def _text(node) -> str:
    if node is None:
        return ""
    return str(getattr(node, "get_text", lambda **_: str(node))(strip=True))


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
    style = (td.get("style") or "").replace(" ", "").lower() if td else ""
    return "display:none" not in style


def _is_valid_ability_name(name: str) -> bool:
    return bool(name) and name.lower() not in {"ability", "abilities", "hidden ability"}


def _full_image_url(src: str) -> str:
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("http"):
        return src
    return BULBAPEDIA_IMAGE_BASE + src


def _safe_form_key(label: str) -> str:
    s = re.sub(r"\s+form\s*$", "", (label or "").strip(), flags=re.I)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "_", s).strip("_")
    return s or "default"


def _is_acceptable_form_label(form_label: str, name_norm: str) -> bool:
    if not form_label or "{{{" in form_label:
        return False
    lower = form_label.lower()
    if "form" in lower or "mega" in lower:
        return True
    return bool(name_norm and lower == name_norm)


def _is_infobox_table(tag) -> bool:
    if tag is None or getattr(tag, "name", None) != "table":
        return False
    classes = tag.get("class") or []
    return any("roundy" in c or "infobox" in c for c in classes)


class BulbapediaSoupParser:
    """Parser da Bulbapedia usando BeautifulSoup."""

    def parse(self, html_content: str, page_name: Optional[str] = None) -> Pokemon:
        soup = BeautifulSoup(html_content, "html.parser")
        infobox_tables = soup.find_all(_is_infobox_table)

        name = self._extract_name(soup, page_name)
        national_dex_number = self._extract_national_dex(infobox_tables)
        category = self._extract_category(soup)
        types = self._extract_types(infobox_tables)
        base_stats = self._extract_base_stats(soup)
        abilities = self._extract_abilities(soup, infobox_tables)
        evolution_prev, evolution_next = self._extract_evolutions(soup, current_name=name)
        gender_ratio = self._extract_gender_ratio(soup)

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
            gender_ratio=gender_ratio,
        )

    def get_image_url(self, html_content: str, pokemon_name: Optional[str] = None) -> Optional[str]:
        specs = self.get_image_specs(html_content, pokemon_name)
        return specs[0][1] if specs else None

    def get_image_specs(
        self, html_content: str, pokemon_name: Optional[str] = None
    ) -> list[tuple[Optional[str], str]]:
        soup = BeautifulSoup(html_content, "html.parser")
        all_infobox = soup.find_all(_is_infobox_table)
        main_infobox = all_infobox[:1]

        form_specs = self._extract_form_image_specs_from_infobox(main_infobox, pokemon_name=pokemon_name)
        if len(form_specs) >= MIN_FORMS_FOR_MULTI_IMAGE:
            return form_specs
        return self._extract_image_specs(main_infobox, pokemon_name=pokemon_name)

    async def extract_and_download_form_images(
        self,
        html_content: str,
        pokemon: Pokemon,
        downloader: "ImageDownloader",
    ) -> list[tuple[Optional[str], str]]:
        specs = self.get_image_specs(html_content, pokemon.name)
        if not specs:
            return []
        return await downloader.download_forms_async(pokemon, specs)

    # ---- Extractors ----

    def _extract_name(self, soup: BeautifulSoup, page_name: Optional[str]) -> str:
        h1 = soup.find("h1", id="firstHeading")
        if not h1:
            return ""
        text = _text(h1)
        return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()

    def _extract_national_dex(self, infobox_tables) -> Optional[int]:
        for table in infobox_tables:
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"], recursive=False)
                for i, cell in enumerate(cells):
                    text = _text(cell)
                    m = re.search(r"#?\s*(\d{3,4})\s*$", text)
                    if m:
                        return _safe_int(m.group(1))
                    lower = text.lower()
                    if "national" in lower and "dex" in lower and i + 1 < len(cells):
                        return _safe_int(_text(cells[i + 1]))
        return None

    def _extract_category(self, soup: BeautifulSoup) -> Optional[str]:
        a = soup.find("a", title="Pokémon category")
        t = _text(a)
        return t or None

    def _extract_types(self, infobox_tables) -> list[str]:
        for table in infobox_tables:
            type_anchor = table.find("a", title="Type")
            if not type_anchor:
                continue
            section_td = type_anchor.find_parent("td")
            if not section_td:
                continue
            types: list[str] = []
            for td in section_td.find_all("td"):
                if not _td_is_visible(td):
                    continue
                for a in td.find_all("a", href=True):
                    href = a.get("href") or ""
                    if "(type)" not in href and "(Type)" not in href:
                        continue
                    b = a.find("b")
                    name = _text(b) if b else _text(a)
                    t = _normalize_type(name)
                    if t and t not in types and t.lower() != "unknown":
                        types.append(t)
            if types:
                return types[:2]
        return []

    def _extract_base_stats(self, soup: BeautifulSoup) -> BaseStats:
        span = soup.find("span", id="Base_stats")
        if not span:
            return BaseStats()
        h4 = span.find_parent("h4")
        if not h4:
            return BaseStats()
        table = h4.find_next_sibling(lambda t: getattr(t, "name", None) == "table")
        if not table:
            return BaseStats()

        stats: dict[str, int] = {}
        for row in table.find_all("tr"):
            th = row.find("th")
            if not th:
                continue
            divs = th.find_all("div", recursive=False)
            if len(divs) < 2:
                continue
            stat_name = _text(divs[0]).replace(":", "").strip().lower()
            stat_value = _text(divs[1])
            key = {
                "hp": "hp",
                "attack": "attack",
                "defense": "defense",
                "sp atk": "sp_atk",
                "sp. atk": "sp_atk",
                "sp def": "sp_def",
                "sp. def": "sp_def",
                "speed": "speed",
            }.get(stat_name)
            if not key:
                continue
            val = _safe_int(stat_value)
            if val is None or not (0 <= val <= 255):
                continue
            stats[key] = val
            if len(stats) == 6:
                break

        return BaseStats(
            hp=stats.get("hp", 0),
            attack=stats.get("attack", 0),
            defense=stats.get("defense", 0),
            sp_atk=stats.get("sp_atk", 0),
            sp_def=stats.get("sp_def", 0),
            speed=stats.get("speed", 0),
        )

    def _extract_abilities_from_td(self, td) -> list[AbilityInfo]:
        if not _td_is_visible(td):
            return []
        text = _text(td)
        if not text:
            return []
        hidden = "hidden ability" in text.lower()
        result: list[AbilityInfo] = []

        links = td.find_all("a")
        if links:
            for a in links:
                name = _text(a)
                if _is_valid_ability_name(name):
                    result.append(AbilityInfo(name=name, is_hidden=hidden))
        else:
            for part in re.split(r"[,/]", text):
                part = part.strip()
                if _is_valid_ability_name(part) and "hidden" not in part.lower():
                    result.append(AbilityInfo(name=part, is_hidden=False))
        return result

    def _dedupe_abilities(self, abilities: list[AbilityInfo]) -> list[AbilityInfo]:
        seen: set[tuple[str, bool]] = set()
        out: list[AbilityInfo] = []
        for a in abilities:
            key = (a.name, a.is_hidden)
            if key not in seen:
                seen.add(key)
                out.append(a)
        return out

    def _extract_abilities(self, soup: BeautifulSoup, infobox_tables) -> list[AbilityInfo]:
        # 1) tenta achar a linha 'Ability' no infobox
        for table in infobox_tables:
            for row in table.find_all("tr"):
                th = row.find("th")
                if not th or "ability" not in _text(th).lower():
                    continue
                abilities: list[AbilityInfo] = []
                for td in row.find_all("td", recursive=False):
                    abilities.extend(self._extract_abilities_from_td(td))
                if abilities:
                    return self._dedupe_abilities(abilities)

        # 2) fallback: procurar uma célula que mencione 'abilities' e extrair da tabela dentro
        for cell in soup.find_all(["th", "td"]):
            if "abilities" not in _text(cell).lower():
                continue
            inner_table = cell.find("table", class_=lambda c: c and ("roundy" in c or "infobox" in c))
            if not inner_table:
                continue
            abilities: list[AbilityInfo] = []
            for td in inner_table.find_all("td"):
                abilities.extend(self._extract_abilities_from_td(td))
            if abilities:
                return self._dedupe_abilities(abilities)
        return []

    # ---- Evolution ----

    def _evolution_table_has_stage_and_link(self, table) -> bool:
        stage_re = re.compile(r"^(Unevolved|First Evolution|Second Evolution)$", re.I)
        has_link = bool(
            table.find("a", href=re.compile(r"\(Pok", re.I)) or table.find("a", class_="selflink")
        )
        if not has_link:
            # busca alternativa igual ao lxml: href contendo "(Pok" ou selflink
            has_link = bool(table.find("a", href=lambda h: h and "(Pok" in h) or table.find("a", class_="selflink"))
        if not has_link:
            return False
        for s in table.find_all("small"):
            if stage_re.match(_text(s)):
                return True
        return False

    def _find_valid_evolution_tables(self, evolution_div) -> list:
        if evolution_div is None:
            return []
        result = []
        for table in evolution_div.find_all("table"):
            if not self._evolution_table_has_stage_and_link(table):
                continue
            nested = any(self._evolution_table_has_stage_and_link(t) for t in table.find_all("table"))
            if nested:
                continue
            result.append(table)
        return result

    def _extract_form_name(self, table) -> Optional[str]:
        stage_re = re.compile(r"^(Unevolved|First Evolution|Second Evolution)$", re.I)
        for s in table.find_all("small"):
            text = _text(s)
            if stage_re.match(text):
                continue
            if text and "Form" in text:
                form_name = text.replace(" Form", "").strip()
                if form_name:
                    return form_name
        return None

    def _parse_evolution_table(self, table) -> Optional[str]:
        stage_re = re.compile(r"^(Unevolved|First Evolution|Second Evolution)$", re.I)
        stage_small = None
        for s in table.find_all("small"):
            if stage_re.match(_text(s)):
                stage_small = s
                break
        if stage_small is None:
            return None
        a = table.find("a", href=lambda h: h and "(Pok" in h) or table.find("a", class_="selflink")
        if not a:
            return None
        name = _text(a)
        if not name or name in ("→", "←", "↗", "↘"):
            return None
        form_name = self._extract_form_name(table)
        if form_name:
            name = f"{name} ({form_name})"
        return name

    def _extract_evolution_chain(self, evolution_div) -> list[str]:
        tables = self._find_valid_evolution_tables(evolution_div)
        chain: list[str] = []
        for table in tables:
            name = self._parse_evolution_table(table)
            if name:
                chain.append(name)
        return chain

    def _resolve_prev_next(
        self, chain: list[str], current_name: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
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
            next_name = chain[idx + 1]
        return (prev_name, next_name)

    def _extract_evolutions(
        self, soup: BeautifulSoup, current_name: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        span = soup.find("span", id="Evolution")
        if not span:
            return (None, None)
        h3 = span.find_parent("h3")
        if not h3:
            return (None, None)
        div = h3.find_next_sibling("div")
        chain = self._extract_evolution_chain(div) if div is not None else []
        return self._resolve_prev_next(chain, current_name)

    # ---- Images ----

    def _image_src_allowed(self, src: str) -> bool:
        return bool(src and re.search(r"(archives|bulbagarden)", src, re.I))

    def _image_src_is_main_artwork(self, src: str) -> bool:
        if not src:
            return False
        lower = src.lower()
        if "candy" in lower or "/go_" in lower:
            return False
        m = re.search(r"/(\d+)px-", src)
        if m:
            try:
                return int(m.group(1)) >= MIN_ARTWORK_PX
            except ValueError:
                return True
        return True

    def _image_matches_pokemon(self, img, name_norm: str, src: Optional[str] = None) -> bool:
        if not name_norm:
            return False
        if src and name_norm in src.lower():
            return True
        alt = (img.get("alt") or "").lower() if img else ""
        title = (img.get("title") or "").lower() if img else ""
        parent = img.find_parent("a") if img else None
        parent_title = (parent.get("title") or "").lower() if parent else ""
        return name_norm in " ".join([alt, title, parent_title])

    def _extract_form_image_specs_from_infobox(
        self,
        infobox_tables,
        pokemon_name: Optional[str] = None,
    ) -> list[tuple[Optional[str], str]]:
        seen: set[str] = set()
        specs: list[tuple[Optional[str], str]] = []
        name_norm = pokemon_name.strip().lower() if pokemon_name else ""
        for table in infobox_tables:
            for span in table.find_all("span", attrs={"typeof": "mw:File"}):
                a = span.find("a", class_="mw-file-description")
                img = a.find("img") if a else None
                if not img:
                    continue
                src = (img.get("src") or "").strip()
                if not src or not self._image_src_allowed(src):
                    continue
                small = span.find_next_sibling("small")
                form_label = _text(small)
                if not _is_acceptable_form_label(form_label, name_norm):
                    continue
                form_key = _safe_form_key(form_label)
                if form_key in seen:
                    continue
                seen.add(form_key)
                specs.append((form_key, _full_image_url(src)))
        return specs

    def _extract_image_specs(
        self, infobox_tables, pokemon_name: Optional[str] = None
    ) -> list[tuple[Optional[str], str]]:
        name_norm = pokemon_name.lower() if pokemon_name else ""
        if not name_norm:
            return []
        for table in infobox_tables:
            for img in table.find_all("img", src=True):
                src = (img.get("src") or "").strip()
                if not src or not self._image_src_allowed(src):
                    continue
                if not self._image_src_is_main_artwork(src):
                    continue
                if not self._image_matches_pokemon(img, name_norm, src=src):
                    continue
                return [(None, _full_image_url(src))]
        return []

    # ---- Gender ratio ----

    def _extract_gender_ratio(self, soup: BeautifulSoup) -> Optional[GenderRatio]:
        def parse_percent(raw: str) -> Optional[float]:
            if not raw:
                return None
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", raw.strip())
            if not m:
                return None
            try:
                return float(m.group(1))
            except ValueError:
                return None

        gender_table = None
        for table in soup.find_all("table"):
            text = table.get_text(" ", strip=True).lower()
            if "gender ratio" in text and ("male" in text or "female" in text):
                gender_table = table
                break
        if not gender_table:
            return None

        male_pct: Optional[float] = None
        female_pct: Optional[float] = None
        for span in gender_table.find_all("span"):
            text = _text(span)
            if not text or "%" not in text:
                continue
            lower = text.lower()
            if "female" in lower:
                female_pct = parse_percent(text)
            elif "male" in lower:
                male_pct = parse_percent(text)

        if male_pct is None and female_pct is None:
            return None
        return GenderRatio(male=male_pct, female=female_pct)

