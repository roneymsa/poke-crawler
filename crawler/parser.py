"""
Parsing do HTML da Bulbapedia com lxml e XPath.
"""

import re
from typing import TYPE_CHECKING, List, Optional

from lxml import html, etree  # type: ignore[import-untyped]

from crawler.domain.models import AbilityInfo, BaseStats, GenderRatio, Pokemon

if TYPE_CHECKING:
    from crawler.downloader import ImageDownloader

BULBAPEDIA_IMAGE_BASE = "https://bulbapedia.bulbagarden.net"

# XPath: tabelas infobox (roundy ou infobox no class)
XPATH_INFOBOX_TABLES = '//table[contains(@class,"roundy") or contains(@class,"infobox")]'
# Formas: span mw:File com a.mw-file-description e following-sibling small com a descrição da forma
XPATH_FORM_IMAGE_SPANS = """.//tr/td/span[@typeof="mw:File"][a[@class="mw-file-description"]][following-sibling::small[normalize-space()]]"""
# Nome: primeiro título da página
XPATH_FIRST_HEADING = '//h1[@id="firstHeading"]'
# Categoria: link com title "Pokémon category"
XPATH_CATEGORY = '//a[@title="Pokémon category"]'
# Base stats: tabela imediatamente após o h4 que contém span#Base_stats
XPATH_BASE_STATS_TABLE = '//span[@id="Base_stats"]/parent::h4/following-sibling::*[self::table][1]'
# Evolution: div irmão seguinte do h3 que contém span#Evolution
XPATH_EVOLUTION_DIV = '//span[@id="Evolution"]/parent::h3/following-sibling::div[1]'
# Tabelas com "gender ratio" no texto
XPATH_GENDER_TABLE = '//table[contains(., "gender ratio")]'

def _text(el) -> str:
    """Texto completo do elemento (incluindo descendentes), normalizado."""
    if el is None:
        return ""
    return (el.text_content() or "").strip()


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
    style = (td.get("style") or "").replace(" ", "").lower()
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
    """Normaliza rótulo de forma para uso em nome de arquivo (ex.: 'Red-Striped Form' -> 'Red_Striped')."""
    s = re.sub(r"\s+form\s*$", "", (label or "").strip(), flags=re.I)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "_", s).strip("_")
    return s or "default"


def _dedupe_abilities(abilities: list[AbilityInfo]) -> list[AbilityInfo]:
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
    """Parser da Bulbapedia usando lxml e XPath."""

    def parse(self, html_content: str, page_name: Optional[str] = None) -> Pokemon:
        tree = html.fromstring(html_content)
        infobox_tables = tree.xpath(XPATH_INFOBOX_TABLES)
        name = self._extract_name(tree, page_name)
        national_dex_number = self._extract_national_dex(infobox_tables)
        category = self._extract_category(tree)
        types = self._extract_types(infobox_tables)
        base_stats = self._extract_base_stats(tree)
        abilities = self._extract_abilities(tree, infobox_tables)
        evolution_prev, evolution_next = self._extract_evolutions(tree, current_name=name)
        gender_ratio = self._extract_gender_ratio(tree)

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
        """Extrai a URL da imagem principal do Pokémon (compatibilidade: retorna a primeira)."""
        specs = self.get_image_specs(html_content, pokemon_name)
        return specs[0][1] if specs else None

    def get_image_specs(
        self, html_content: str, pokemon_name: Optional[str] = None
    ) -> list[tuple[Optional[str], str]]:
        """
        Extrai imagens do infobox: só usa tabela de formas quando há 2+ formas
        (span mw:File + small com texto); senão fallback para uma imagem única.
        Restringe à primeira tabela roundy/infobox (infobox principal), sem sair para outras.
        Retorna [(form_key, url), ...].
        """
        tree = html.fromstring(html_content)
        all_infobox = tree.xpath(XPATH_INFOBOX_TABLES)
        main_infobox = all_infobox[:1]  # só a primeira tabela (infobox principal)
        form_specs = self._extract_form_image_specs_from_infobox(main_infobox)
        # Só ativa extração por formas quando a página tem mais de uma forma (ex.: Basculin)
        if len(form_specs) >= 2:
            return form_specs
        return self._extract_image_specs(main_infobox, pokemon_name=pokemon_name)

    async def extract_and_download_form_images(
        self,
        html_content: str,
        pokemon: Pokemon,
        downloader: "ImageDownloader",
    ) -> list[tuple[Optional[str], str]]:
        """
        Extrai specs de imagens (formas) e baixa cada uma; retorna [(form_key, path), ...].
        O download é feito a partir do parser para centralizar a lógica de formas.
        """
        specs = self.get_image_specs(html_content, pokemon.name)
        if not specs:
            return []
        return await downloader.download_forms_async(pokemon, specs)

    def _extract_name(self, tree: etree._Element, page_name: Optional[str]) -> str:
        nodes = tree.xpath(XPATH_FIRST_HEADING)
        if not nodes:
            return ""
        text = _text(nodes[0])
        return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()

    def _extract_national_dex(self, infobox_tables: List[etree._Element]) -> Optional[int]:
        for table in infobox_tables:
            for row in table.xpath(".//tr"):
                cells = row.xpath("./th | ./td")
                for i, cell in enumerate(cells):
                    text = _text(cell)
                    match = re.search(r"#?\s*(\d{3,4})\s*$", text)
                    if match:
                        return _safe_int(match.group(1))
                    if "national" in text.lower() and "dex" in text.lower() and i + 1 < len(cells):
                        return _safe_int(_text(cells[i + 1]))
        return None

    def _extract_category(self, tree: etree._Element) -> Optional[str]:
        nodes = tree.xpath(XPATH_CATEGORY)
        if not nodes:
            return None
        t = _text(nodes[0])
        return t or None

    def _extract_types(self, infobox_tables: List[etree._Element]) -> list[str]:
        for table in infobox_tables:
            type_anchors = table.xpath('.//a[@title="Type"]')
            if not type_anchors:
                continue
            ancestors = type_anchors[0].xpath("./ancestor::td")
            if not ancestors:
                continue
            section_td = ancestors[0]
            types: list[str] = []
            for td in section_td.xpath(".//td"):
                if not _td_is_visible(td):
                    continue
                for a in td.xpath('.//a[contains(@href,"(type)") or contains(@href,"(Type)")]'):
                    b = a.xpath("./span/b")
                    name = _text(b[0]) if b else _text(a)
                    if not name:
                        continue
                    t = _normalize_type(name)
                    if t and t not in types and t.lower() != "unknown":
                        types.append(t)
            if types:
                return types[:2]
        return []

    def _extract_base_stats(self, tree: etree._Element) -> BaseStats:
        tables = tree.xpath(XPATH_BASE_STATS_TABLE)
        stats: dict[str, int] = {}
        if not tables:
            return self._base_stats_from_map(stats)
        table = tables[0]
        for row in table.xpath(".//tr"):
            th = row.xpath("./th")
            if not th:
                continue
            divs = th[0].xpath("./div")
            if len(divs) < 2:
                continue
            stat_name = _text(divs[0]).replace(":", "").strip().lower()
            stat_value = _text(divs[1])
            key = STAT_MAP.get(stat_name)
            if not key:
                continue
            val = _safe_int(stat_value)
            if val is None or not (0 <= val <= 255):
                continue
            stats[key] = val
            if len(stats) == 6:
                break
        return self._base_stats_from_map(stats)

    def _base_stats_from_map(self, stats: dict[str, int]) -> BaseStats:
        return BaseStats(
            hp=stats.get("hp", 0),
            attack=stats.get("attack", 0),
            defense=stats.get("defense", 0),
            sp_atk=stats.get("sp_atk", 0),
            sp_def=stats.get("sp_def", 0),
            speed=stats.get("speed", 0),
        )

    def _evolution_table_has_stage_and_link(self, table: etree._Element) -> bool:
        link_re = re.compile(r"_\(Pok", re.I)
        stage_re = re.compile(r"^(Unevolved|First Evolution|Second Evolution)$", re.I)
        has_link = table.xpath('.//a[contains(@href,"(Pok") or contains(@class,"selflink")]') or []
        if not has_link:
            return False
        for s in table.xpath(".//small"):
            if stage_re.match(_text(s)):
                return True
        return False

    def _find_valid_evolution_tables(self, evolution_div: Optional[etree._Element]) -> list:
        if evolution_div is None:
            return []
        result = []
        for table in evolution_div.xpath(".//table"):
            if not self._evolution_table_has_stage_and_link(table):
                continue
            nested_valid = any(
                self._evolution_table_has_stage_and_link(t)
                for t in table.xpath(".//table")
            )
            if nested_valid:
                continue
            result.append(table)
        return result

    def _extract_form_name(self, table: etree._Element) -> Optional[str]:
        stage_re = re.compile(r"^(Unevolved|First Evolution|Second Evolution)$", re.I)
        for s in table.xpath(".//small"):
            text = _text(s)
            if stage_re.match(text):
                continue
            if text and "Form" in text:
                form_name = text.replace(" Form", "").strip()
                if form_name:
                    return form_name
        return None

    def _parse_evolution_table(self, table: etree._Element) -> Optional[str]:
        stage_re = re.compile(r"^(Unevolved|First Evolution|Second Evolution)$", re.I)
        stage_small = None
        for s in table.xpath(".//small"):
            if stage_re.match(_text(s)):
                stage_small = s
                break
        if stage_small is None:
            return None
        a_nodes = table.xpath('.//a[contains(@href,"(Pok") or contains(@class,"selflink")]')
        if not a_nodes:
            return None
        name = _text(a_nodes[0])
        if not name or name in ("→", "←", "↗", "↘"):
            return None
        form_name = self._extract_form_name(table)
        if form_name:
            name = f"{name} ({form_name})"
        return name

    def _extract_evolution_chain(self, evolution_div: Optional[etree._Element]) -> list[str]:
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
        self, tree: etree._Element, current_name: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        divs = tree.xpath(XPATH_EVOLUTION_DIV)
        div = divs[0] if divs else None
        chain = self._extract_evolution_chain(div) if div is not None else []
        return self._resolve_prev_next(chain, current_name)

    def _extract_abilities_from_td(self, td: etree._Element) -> list[AbilityInfo]:
        if not _td_is_visible(td):
            return []
        text = _text(td)
        if not text:
            return []
        hidden = "hidden ability" in text.lower()
        result: list[AbilityInfo] = []
        links = td.xpath(".//a")
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

    def _extract_abilities(self, tree: etree._Element, infobox_tables: List[etree._Element]) -> list[AbilityInfo]:
        for table in infobox_tables:
            for row in table.xpath(".//tr"):
                th_list = row.xpath("./th")
                if not th_list or "ability" not in _text(th_list[0]).lower():
                    continue
                abilities: list[AbilityInfo] = []
                for td in row.xpath("./td"):
                    abilities.extend(self._extract_abilities_from_td(td))
                if abilities:
                    return _dedupe_abilities(abilities)
        for cell in tree.xpath("//th | //td"):
            if "abilities" not in _text(cell).lower():
                continue
            tables = cell.xpath(
                './/table[contains(@class,"roundy") or contains(@class,"infobox")][1]'
            )
            if not tables:
                continue
            abilities = []
            for td in tables[0].xpath(".//td"):
                abilities.extend(self._extract_abilities_from_td(td))
            if abilities:
                return _dedupe_abilities(abilities)
        return []

    def _extract_form_image_specs_from_infobox(
        self, infobox_tables: List[etree._Element]
    ) -> list[tuple[Optional[str], str]]:
        """
        Extrai (form_key, url) a partir da tabela de formas: span[@typeof="mw:File"]
        com a[@class="mw-file-description"] (img) e following-sibling::small (descrição).
        Só retorna entradas com src permitido e small com texto.
        """
        seen: set[str] = set()
        specs: list[tuple[Optional[str], str]] = []
        for table in infobox_tables:
            for span in table.xpath(XPATH_FORM_IMAGE_SPANS):
                imgs = span.xpath('.//a[@class="mw-file-description"]/img/@src')
                smalls = span.xpath("following-sibling::small[1]")
                if not imgs:
                    continue
                src = (imgs[0] or "").strip()
                if not src or not self._image_src_allowed(src):
                    continue
                form_label = _text(smalls[0]).strip() if smalls else ""
                if not form_label or "{{{" in form_label:
                    continue
                if "form" not in form_label.lower():
                    continue
                form_key = _safe_form_key(form_label)
                if form_key in seen:
                    continue
                seen.add(form_key)
                url = _full_image_url(src)
                specs.append((form_key, url))
        if not specs:
            return []
        return specs

    def _image_src_allowed(self, src: str) -> bool:
        return bool(src and re.search(r"(archives|bulbagarden)", src, re.I))

    def _image_matches_pokemon(
        self, img: etree._Element, name_norm: str, src: Optional[str] = None
    ) -> bool:
        """True se a imagem pertence ao Pokémon (alt/title/parent ou nome no src)."""
        if not name_norm:
            return False
        if src and name_norm in src.lower():
            return True
        alt = (img.get("alt") or "").lower()
        title = (img.get("title") or "").lower()
        parent = img.xpath("./parent::a")
        parent_title = (parent[0].get("title") or "").lower() if parent else ""
        return name_norm in " ".join([alt, title, parent_title])

    def _image_src_is_main_artwork(self, src: str) -> bool:
        """Exclui thumbnails pequenos e ícones (Candy, GO_, /20px-, /40px-, /96px-)."""
        if not src:
            return False
        lower = src.lower()
        if "candy" in lower or "/go_" in lower:
            return False
        if re.search(r"/\d+px-", src):
            px = re.findall(r"/(\d+)px-", src)
            if px and int(px[0]) < 100:
                return False
        return True

    def _extract_image_specs(
        self, infobox_tables: List[etree._Element], pokemon_name: Optional[str] = None
    ) -> list[tuple[Optional[str], str]]:
        """
        Fallback quando não há tabela de formas: retorna a primeira imagem do infobox
        que pertence ao Pokémon (por alt/title ou nome no src), permitida e artwork principal.
        """
        name_norm = pokemon_name.lower() if pokemon_name else None
        if not name_norm:
            return []
        for table in infobox_tables:
            for img in table.xpath(".//img[@src]"):
                src = img.get("src") or ""
                if not src or not self._image_src_allowed(src):
                    continue
                if not self._image_src_is_main_artwork(src):
                    continue
                if not self._image_matches_pokemon(img, name_norm, src=src):
                    continue
                return [(None, _full_image_url(src))]
        return []

    def _extract_gender_ratio(self, tree: etree._Element) -> Optional[GenderRatio]:
        tables = tree.xpath(XPATH_GENDER_TABLE)
        if not tables:
            return None
        gender_table = tables[0]

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

        male_pct: Optional[float] = None
        female_pct: Optional[float] = None
        for span in gender_table.xpath(".//span"):
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
