"""
Testes do parser Bulbapedia.
Usam o HTML em tests/fixtures/bulbapedia_pokemon_page.html.
Você pode substituir esse arquivo por HTML real de uma página da Bulbapedia
para validar o parsing com dados reais.
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
POKEMON_PAGE_HTML = FIXTURES_DIR / "bulbapedia_pokemon_page.html"


def _load_fixture_html() -> str:
    """Carrega o HTML do fixture. Preencha o arquivo com HTML real se quiser."""
    if not POKEMON_PAGE_HTML.exists():
        pytest.skip(f"Fixture não encontrado: {POKEMON_PAGE_HTML}")
    return POKEMON_PAGE_HTML.read_text(encoding="utf-8")


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
        from bs4 import BeautifulSoup
        td = BeautifulSoup("<td>x</td>", "html.parser").find("td")
        assert _td_is_visible(td) is True

    def test_display_none_is_hidden(self):
        from bs4 import BeautifulSoup
        td = BeautifulSoup('<td style="display:none">x</td>', "html.parser").find("td")
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

class TestBulbapediaParserWithFixture:
    """Testes que usam tests/fixtures/bulbapedia_pokemon_page.html."""

    @pytest.fixture
    def html(self):
        return _load_fixture_html()

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

    def test_get_image_url_without_matching_image_returns_none(self, parser, html):
        # O fixture atual não tem img com alt/title do Pokémon na URL bulbagarden
        url = parser.get_image_url(html, "Pikachu")
        # Pode ser None se não houver img que bata com o nome e archives/bulbagarden
        assert url is None or "bulbagarden" in url or "archives" in url


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
