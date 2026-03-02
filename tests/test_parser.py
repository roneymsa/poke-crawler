"""
Testes do parser Bulbapedia.
Usam os HTML em tests/fixtures/bulbapedia_*.html.
Cada fixture é rodado nos testes parametrizados; testes com valores exatos
usam bulbapedia_pikachu.html.
"""

import pytest
from pathlib import Path

from crawler.parser import (
    BulbapediaParser,
    _safe_int,
    _normalize_type,
    _td_is_visible,
    _is_valid_ability_name,
    _full_image_url,
    _dedupe_abilities,
)
from crawler.domain.models import AbilityInfo, BaseStats, Pokemon


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
# Fixture usado pelos testes que checam valores exatos (Pikachu)
PIKACHU_FIXTURE = FIXTURES_DIR / "bulbapedia_pikachu.html"


def _all_bulbapedia_fixtures():
    """Lista (path, expected_name) de todos os fixtures bulbapedia_*.html."""
    if not FIXTURES_DIR.exists():
        return []
    out = []
    for p in sorted(FIXTURES_DIR.glob("bulbapedia_*.html")):
        # bulbapedia_pikachu.html -> "Pikachu", bulbapedia_bulbasaur.html -> "Bulbasaur"
        stem = p.stem
        if stem.startswith("bulbapedia_"):
            name_part = stem.replace("bulbapedia_", "", 1)
            expected_name = name_part.replace("_", " ").title()
            out.append((p, expected_name))
    return out


def _load_fixture_html(path: Path) -> str:
    """Carrega o HTML do fixture no path."""
    if not path.exists():
        pytest.skip(f"Fixture não encontrado: {path}")
    return path.read_text(encoding="utf-8")


# ---- Testes das funções auxiliares (módulo) ----

class TestSafeInt:
    def test_none_returns_none(self):
        assert _safe_int(None) is None

    def test_empty_string_returns_none(self):
        assert _safe_int("") is None
        assert _safe_int("   ") is None

    def test_valid_int(self):
        assert _safe_int("42") == 42
        assert _safe_int("  100  ") == 100

    def test_comma_removed(self):
        assert _safe_int("1,000") == 1000

    def test_invalid_returns_none(self):
        assert _safe_int("abc") is None
        assert _safe_int("12.5") is None


class TestNormalizeType:
    def test_strips_parentheses_suffix(self):
        assert _normalize_type("Fire (original)") == "Fire"

    def test_empty_after_strip_returns_empty(self):
        assert _normalize_type("") == ""
        assert _normalize_type("   ") == ""


class TestTdIsVisible:
    def test_no_style_is_visible(self):
        from lxml import html as lxml_html
        td = lxml_html.fromstring("<td>x</td>")
        assert _td_is_visible(td) is True

    def test_display_none_is_hidden(self):
        from lxml import html as lxml_html
        td = lxml_html.fromstring('<td style="display:none">x</td>')
        assert _td_is_visible(td) is False


class TestIsValidAbilityName:
    def test_valid_names(self):
        assert _is_valid_ability_name("Static") is True
        assert _is_valid_ability_name("Lightning Rod") is True

    def test_invalid_labels(self):
        assert _is_valid_ability_name("ability") is False
        assert _is_valid_ability_name("Ability") is False
        assert _is_valid_ability_name("abilities") is False
        assert _is_valid_ability_name("hidden ability") is False

    def test_empty_false(self):
        assert _is_valid_ability_name("") is False


class TestFullImageUrl:
    def test_empty_returns_empty(self):
        assert _full_image_url("") == ""

    def test_protocol_relative(self):
        assert _full_image_url("//archives.bulbagarden.net/x.png") == "https://archives.bulbagarden.net/x.png"

    def test_absolute_unchanged(self):
        assert _full_image_url("https://example.com/a.png") == "https://example.com/a.png"

    def test_relative_prepends_base(self):
        assert "/media/foo.png" in _full_image_url("/media/foo.png")
        assert _full_image_url("/media/foo.png").startswith("https://bulbapedia.bulbagarden.net")


class TestDedupeAbilities:
    def test_removes_duplicate_name_and_hidden(self):
        abils = [
            AbilityInfo(name="Static", is_hidden=False),
            AbilityInfo(name="Static", is_hidden=False),
            AbilityInfo(name="Lightning Rod", is_hidden=True),
        ]
        out = _dedupe_abilities(abils)
        assert len(out) == 2
        assert out[0].name == "Static"
        assert out[1].name == "Lightning Rod"

    def test_same_name_different_hidden_kept(self):
        abils = [
            AbilityInfo(name="Static", is_hidden=False),
            AbilityInfo(name="Static", is_hidden=True),
        ]
        out = _dedupe_abilities(abils)
        assert len(out) == 2


# ---- Testes do BulbapediaParser (fixture HTML) ----

# Todos os fixtures para testes parametrizados: (path, nome esperado do arquivo)
_ALL_FIXTURES = _all_bulbapedia_fixtures()
BULBAPEDIA_FIXTURE_IDS = [(p, name) for p, name in _ALL_FIXTURES]
FIXTURE_IDS_NAMES = [p.stem for p, _ in _ALL_FIXTURES]
@pytest.mark.parametrize("fixture_path,expected_name_from_file", BULBAPEDIA_FIXTURE_IDS, ids=FIXTURE_IDS_NAMES)
class TestBulbapediaParserEachFixture:
    """Testes que rodam com cada fixture em tests/fixtures/bulbapedia_*.html."""

    def test_parse_returns_pokemon(self, fixture_path, expected_name_from_file):
        html = _load_fixture_html(fixture_path)
        parser = BulbapediaParser()
        pokemon = parser.parse(html)
        assert isinstance(pokemon, Pokemon)
        assert pokemon.name  # nome extraído não vazio

    def test_parse_has_types_list(self, fixture_path, expected_name_from_file):
        html = _load_fixture_html(fixture_path)
        parser = BulbapediaParser()
        pokemon = parser.parse(html)
        assert isinstance(pokemon.types, list)

    def test_parse_has_base_stats(self, fixture_path, expected_name_from_file):
        html = _load_fixture_html(fixture_path)
        parser = BulbapediaParser()
        pokemon = parser.parse(html)
        assert pokemon.base_stats is not None
        assert isinstance(pokemon.base_stats, BaseStats)

class TestBulbapediaParserWithFixture:
    """Testes com valores exatos usando tests/fixtures/bulbapedia_pikachu.html."""

    @pytest.fixture
    def html(self):
        return _load_fixture_html(PIKACHU_FIXTURE)

    @pytest.fixture
    def parser(self):
        return BulbapediaParser()

    def test_parse_returns_pokemon(self, parser, html):
        pokemon = parser.parse(html)
        assert isinstance(pokemon, Pokemon)
        assert pokemon.name == "Pikachu"

    def test_parse_extracts_name(self, parser, html):
        pokemon = parser.parse(html)
        assert pokemon.name == "Pikachu"

    def test_parse_extracts_national_dex(self, parser, html):
        pokemon = parser.parse(html)
        assert pokemon.national_dex_number == 25

    def test_parse_extracts_category(self, parser, html):
        pokemon = parser.parse(html)
        assert pokemon.category == "Mouse Pokémon"

    def test_parse_extracts_types(self, parser, html):
        pokemon = parser.parse(html)
        assert "Electric" in pokemon.types

    def test_parse_extracts_base_stats(self, parser, html):
        pokemon = parser.parse(html)
        assert pokemon.base_stats.hp == 35
        assert pokemon.base_stats.speed == 90

    def test_parse_extracts_abilities(self, parser, html):
        pokemon = parser.parse(html)
        names = [a.name for a in pokemon.abilities]
        assert "Static" in names
        assert "Lightning Rod" in names

    def test_parse_extracts_evolution_prev_next(self, parser, html):
        pokemon = parser.parse(html, page_name="Pikachu")
        assert pokemon.evolution_prev == "Pichu"
        assert pokemon.evolution_next == "Raichu"

    def test_parse_extracts_gender_ratio(self, parser, html):
        pokemon = parser.parse(html, page_name="Pikachu")
        assert pokemon.gender_ratio is not None
        assert pokemon.gender_ratio.male == 50.0
        assert pokemon.gender_ratio.female == 50.0

    def test_get_image_url_without_matching_image_returns_none(self, parser, html):
        # O fixture atual não tem img com alt/title do Pokémon na URL bulbagarden
        url = parser.get_image_url(html, "Pikachu")
        # Pode ser None se não houver img que bata com o nome e archives/bulbagarden
        assert url is None or "bulbagarden" in url or "archives" in url

class TestBulbapediaParserNidoran:
    """Testes específicos para coleta de Nidoran♀ e Nidoran♂ (duas páginas distintas)."""

    @pytest.fixture
    def parser(self):
        return BulbapediaParser()

    def test_nidoran_female_parse(self, parser):
        """Nidoran♀: nome, dex, categoria, tipos, stats e evolução extraídos do fixture."""
        path = FIXTURES_DIR / "bulbapedia_nidoran♀.html"
        html = _load_fixture_html(path)
        pokemon = parser.parse(html, page_name="Nidoran♀")
        assert pokemon.name == "Nidoran♀"
        assert pokemon.national_dex_number == 29
        assert pokemon.category == "Poison Pin Pokémon"
        assert "Poison" in pokemon.types
        assert pokemon.base_stats.hp == 55
        assert pokemon.base_stats.attack == 47
        assert pokemon.base_stats.defense == 52
        assert pokemon.base_stats.speed == 41
        assert pokemon.evolution_next == "Nidorina"
        ability_names = [a.name for a in pokemon.abilities]
        assert "Poison Point" in ability_names
        assert "Rivalry" in ability_names

    def test_nidoran_male_parse(self, parser):
        """Nidoran♂: nome, dex, categoria, tipos, stats e evolução extraídos do fixture."""
        path = FIXTURES_DIR / "bulbapedia_nidoran♂.html"
        html = _load_fixture_html(path)
        pokemon = parser.parse(html, page_name="Nidoran♂")
        assert pokemon.name == "Nidoran♂"
        assert pokemon.national_dex_number == 32
        assert pokemon.category == "Poison Pin Pokémon"
        assert "Poison" in pokemon.types
        assert pokemon.base_stats.hp == 46
        assert pokemon.base_stats.attack == 57
        assert pokemon.base_stats.defense == 40
        assert pokemon.base_stats.speed == 50
        assert pokemon.evolution_next == "Nidorino"
        ability_names = [a.name for a in pokemon.abilities]
        assert "Poison Point" in ability_names
        assert "Rivalry" in ability_names

    def test_nidoran_female_and_male_are_different(self, parser):
        """Garante que Nidoran♀ e Nidoran♂ produzem dados distintos (dex, stats)."""
        html_f = _load_fixture_html(FIXTURES_DIR / "bulbapedia_nidoran♀.html")
        html_m = _load_fixture_html(FIXTURES_DIR / "bulbapedia_nidoran♂.html")
        p_f = parser.parse(html_f, page_name="Nidoran♀")
        p_m = parser.parse(html_m, page_name="Nidoran♂")
        assert p_f.name != p_m.name
        assert p_f.national_dex_number == 29
        assert p_m.national_dex_number == 32
        assert p_f.base_stats.hp == 55 and p_m.base_stats.hp == 46
        assert p_f.evolution_next == "Nidorina" and p_m.evolution_next == "Nidorino"


class TestBulbapediaParserBasculinImage:
    """Basculin tem 3 formas (Red/Blue/White); extração genérica por alt/title e src."""

    def test_basculin_image_specs_returns_three_forms(self):
        path = FIXTURES_DIR / "bulbapedia_basculin.html"
        html = _load_fixture_html(path)
        parser = BulbapediaParser()
        specs = parser.get_image_specs(html, "Basculin")
        assert len(specs) == 3
        form_keys = {k for k, _ in specs}
        assert "Red_Striped" in form_keys
        assert "Blue_Striped" in form_keys
        assert "White_Striped" in form_keys
        urls = [u for _, u in specs]
        assert any("basculin-red" in u.lower() for u in urls)
        assert any("basculin-blue" in u.lower() for u in urls)
        assert any("basculin-white" in u.lower() for u in urls)

    def test_basculin_get_image_url_returns_first_form(self):
        path = FIXTURES_DIR / "bulbapedia_basculin.html"
        html = _load_fixture_html(path)
        parser = BulbapediaParser()
        url = parser.get_image_url(html, "Basculin")
        assert url is not None
        assert "basculin-red" in url.lower()


class TestBulbapediaParserCharmanderImage:
    """Charmander não tem formas alternativas; deve retornar só a imagem principal."""

    def test_charmander_image_specs_returns_single_main_image(self):
        path = FIXTURES_DIR / "bulbapedia_charmander.html"
        html = _load_fixture_html(path)
        parser = BulbapediaParser()
        specs = parser.get_image_specs(html, "Charmander")
        assert len(specs) == 1
        form_key, url = specs[0]
        assert form_key is None
        assert url is not None
        assert "0004charmander" in url.lower()
        assert "250px" in url or "500px" in url or "375px" in url


class TestBulbapediaParserDragoniteImage:
    """Dragonite tem forma normal + Mega; deve retornar as duas imagens."""

    def test_dragonite_image_specs_returns_default_and_mega(self):
        path = FIXTURES_DIR / "bulbapedia_dragonite.html"
        html = _load_fixture_html(path)
        parser = BulbapediaParser()
        specs = parser.get_image_specs(html, "Dragonite")
        assert len(specs) == 2
        form_keys = {k for k, _ in specs}
        urls = [u for _, u in specs]
        assert "Dragonite" in form_keys
        assert "Mega_Dragonite" in form_keys
        assert any("0149dragonite.png" in u.lower() and "mega" not in u.lower() for u in urls)
        assert any("dragonite-mega" in u.lower() for u in urls)


class TestBulbapediaParserEdgeCases:
    def test_parse_empty_html_returns_empty_name(self):
        parser = BulbapediaParser()
        pokemon = parser.parse("<html><body></body></html>")
        assert pokemon.name == ""
        assert pokemon.types == []
        assert pokemon.base_stats.hp == 0

    def test_parse_with_page_name_uses_heading_when_present(self):
        parser = BulbapediaParser()
        html = "<html><body><h1 id=\"firstHeading\">Pikachu (Pokémon)</h1></body></html>"
        pokemon = parser.parse(html, page_name="Other")
        assert pokemon.name == "Pikachu"
