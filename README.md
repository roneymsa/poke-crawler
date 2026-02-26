# Poké-Crawler (Bulbapedia)

Crawler que extrai informações detalhadas de Pokémon a partir do portal [Bulbapedia](https://bulbapedia.bulbagarden.net/). Para cada Pokémon são coletados: nome, número nacional, categoria, tipos, base stats, evoluções, habilidades (com indicação de Hidden Ability) e imagem (salva em pasta local).

## Estrutura do projeto

```
poke-crawler/
├── main.py              # Ponto de entrada e orquestração
├── requirements.txt
├── Dockerfile           # Imagem para rodar o crawler
├── docker-compose.yml   # Orquestração com volume montado
├── crawler/
│   ├── __init__.py
│   ├── client.py        # HTTP (httpx) com retries
│   ├── parser.py        # Extração com BeautifulSoup
│   ├── models.py        # Modelos Pydantic
│   ├── storage.py       # Exportação JSON e SQLite
│   └── downloader.py    # Download de imagens
└── images/              # Fotos dos Pokémon (criada ao rodar)
```

## Requisitos

- Python 3.10+
- Dependências em `requirements.txt`: `httpx`, `beautifulsoup4`, `pydantic`, `tenacity`

## Como rodar

### Opção A: Docker (recomendado)

**Pré-requisito:** [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/install/) instalados.

O projeto monta o diretório atual no container, então os arquivos gerados (`pokemon.json`, `pokemon.db`, `images/`) ficam na pasta do projeto.

```bash
# Usar lista de nomes (crie pokemon_names.txt com um nome por linha)
docker compose run --rm crawler

# Ou passar argumentos (sobrescreve o comando padrão)
docker compose run --rm crawler Pikachu Charmander Squirtle
docker compose run --rm crawler --list pokemon_names.txt --workers 5
docker compose run --rm crawler --list pokemon_names.txt --json output/saida.json --images output/img # Para direcionar as imagens pra pasta output ao invés do padrão
```

Build manual da imagem (opcional):

```bash
docker compose build
```

### Opção B: Ambiente local (Python)

#### 1. Ambiente

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

#### 2. Executar

**Nomes na linha de comando:**

```bash
python main.py Bulbasaur Charmander Squirtle
```

**Lista em arquivo (um nome por linha):**

```bash
python main.py --list pokemon_names.txt
```

**Opções:**

| Argumento | Descrição | Default |
|-----------|------------|---------|
| `NOMES` | Nomes dos Pokémon (posicional) | — |
| `--list` / `-l FILE` | Arquivo com um nome por linha | — |
| `--json` / `-j FILE` | Caminho do arquivo JSON | `pokemon.json` |
| `--db FILE` | Caminho do banco SQLite | `pokemon.db` |
| `--images` / `-i DIR` | Pasta para salvar imagens | `images` |
| `--workers` / `-w N` | Requisições em paralelo | `3` |
| `--no-json` | Não gerar JSON (apenas SQLite) | — |

**Exemplos por argumento:**

```bash
# JSON em arquivo customizado
python main.py Pikachu --json saida.json

# Só SQLite (sem JSON)
python main.py Pikachu --no-json

# SQLite em pasta específica
python main.py Pikachu --db data/pokemon.db

# Imagens em outra pasta
python main.py Pikachu --images assets/sprites

# Mais requisições em paralelo (ex.: 5)
python main.py --list lista.txt --workers 5
```

**Exemplo usando vários argumentos:**

```bash
python main.py --list pokemon_names.txt --json dados.json --db dados.db --images img --workers 4
```

### 3. Saída

- **JSON**: arquivo com array de objetos (um por Pokémon), com todos os campos e caminho da imagem.
- **SQLite**: tabela `pokemon` com os mesmos dados; habilidades em JSON na coluna `abilities`.
- **Imagens**: arquivos em `images/` (ou no diretório indicado por `--images`), com nome derivado do Pokémon (ex.: `Bulbasaur.png`).
