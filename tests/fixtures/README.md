# Fixtures de teste

HTML de páginas da Bulbapedia usados pelos testes do parser em `tests/test_parser.py`.

## Como os testes usam os fixtures

- **Todos os `bulbapedia_*.html`**: os testes parametrizados (`TestBulbapediaParserEachFixture`) rodam com cada arquivo — validam que o parse retorna um `Pokemon` com nome, tipos e base stats.
- **`bulbapedia_pikachu.html`**: os testes com valores exatos (nome, número na dex, tipos, stats, habilidades, evoluções) usam este fixture.

Ao adicionar um novo arquivo `bulbapedia_<nome>.html` na pasta, ele passa a ser incluído automaticamente nos testes parametrizados.

## Fixtures disponíveis

| Arquivo | Pokémon |
|---------|---------|
| `bulbapedia_beldum.html` | Beldum |
| `bulbapedia_bulbasaur.html` | Bulbasaur |
| `bulbapedia_charmander.html` | Charmander |
| `bulbapedia_dragonite.html` | Dragonite |
| `bulbapedia_pichu.html` | Pichu |
| `bulbapedia_pidgey.html` | Pidgey |
| `bulbapedia_pikachu.html` | Pikachu |
| `bulbapedia_squirtle.html` | Squirtle |
| `bulbapedia_teste.html` | teste (placeholder) |

## Como atualizar ou adicionar fixtures

1. Abra a página na Bulbapedia (ex.: https://bulbapedia.bulbagarden.net/wiki/Pikachu_(Pokémon)).
2. Botão direito → "Ver código-fonte da página" (ou Salvar como).
3. Copie o HTML e salve no arquivo correspondente em `tests/fixtures/` (ex.: `bulbapedia_pikachu.html`), ou crie um novo `bulbapedia_<nome>.html`.
