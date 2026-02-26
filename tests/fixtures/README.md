# Fixtures de teste

## `bulbapedia_pokemon_page.html`

HTML de uma página de Pokémon da Bulbapedia usado pelos testes do parser.

**Como usar com HTML real:**

1. Abra uma página na Bulbapedia, por exemplo:
   - https://bulbapedia.bulbagarden.net/wiki/Pikachu_(Pokémon)
2. Clique com o botão direito → "Ver código-fonte da página" (ou Salvar como).
3. Copie o HTML e substitua o conteúdo de `bulbapedia_pokemon_page.html` (ou salve o arquivo completo aqui).

Os testes em `tests/test_parser.py` vão usar esse HTML para validar nome, número na dex, tipos, stats, habilidades e evoluções. Se a estrutura da Bulbapedia mudar, os testes ajudam a identificar o que quebrou.
