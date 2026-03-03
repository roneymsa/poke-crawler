# Poké-Crawler (Bulbapedia)

Crawler que extrai informações detalhadas de Pokémon a partir do portal [Bulbapedia](https://bulbapedia.bulbagarden.net/). Para cada Pokémon são coletados: nome, número nacional, categoria, tipos, base stats, evoluções, habilidades (com indicação de Hidden Ability) e imagem (salva em pasta local).

### Dados coletados (JSON público)

O worker do GitHub Actions exporta os Pokémon já coletados para JSON e faz commit no repositório. Quem clonar o repo ou acessar o link **raw** do arquivo vê os últimos resultados:

- **Link (substitua `SEU_USUARIO` e `poke-crawler` pelo seu usuário/repo):**  
  `https://raw.githubusercontent.com/SEU_USUARIO/poke-crawler/main/data/pokemon_export.json`

Arquivo gerado automaticamente a cada run do workflow *Pokémon worker* (apenas Pokémon com `status=done`).

## Estrutura do projeto

Organização em **Domain Driven Design (DDD)**: domínio em `crawler/domain/` (modelos, serviços, exceções); infra e aplicação em `crawler/` e `main.py`.

```
poke-crawler/
├── main.py                    # Ponto de entrada e orquestração
├── requirements.txt
├── Dockerfile                 # Imagem para rodar o crawler
├── docker-compose.yml        # Orquestração com volume montado
├── crawler/
│   ├── __init__.py
│   ├── client.py             # HTTP (httpx) com retries
│   ├── parser.py             # Extração com BeautifulSoup
│   ├── search.py             # Usa a api do bubapedia pra validar uma busca de nome
│   ├── national_dex.py       # Extração de links da National Pokédex (--get-all)
│   ├── downloader.py         # Download de imagens
│   └── domain/               # Domínio (DDD)
│       ├── __init__.py
│       ├── exceptions.py     # Exceções de domínio
│       ├── models/           # Entidades e value objects (Pydantic)
│       │   ├── __init__.py
│       │   └── pokemon.py
│       └── services/         # Serviços de domínio
│           ├── __init__.py
│           └── storage.py    # Exportação JSON e SQLite
├── tests/
│   ├── test_parser.py
│   └── fixtures/             # HTML da Bulbapedia para testes
└── images/                   # Fotos dos Pokémon (criada ao rodar)
```

## Requisitos

- Python 3.10+
- Dependências em `requirements.txt`: `httpx`, `lxml`, `pydantic`, `tenacity`, `pytest`, `flake8`

## Como rodar

### Opção A: Docker (recomendado)

**Pré-requisito:** [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/install/) instalados.

O projeto monta o diretório atual no container, então os arquivos gerados (`pokemon.json`, `pokemon.db`, `images/`) ficam na pasta do projeto.

**Executar o crawler:**

```bash
# Usar lista de nomes (crie pokemon_names.txt com um nome por linha)
docker compose run --rm crawler

# Passar nomes na linha de comando
docker compose run --rm crawler Pikachu Charmander Squirtle

# Lista em arquivo e mais workers
docker compose run --rm crawler --list pokemon_names.txt --workers 5

# Extrair todos os Pokémon da National Pokédex (salva em todos_pokemons.json / todos_pokemons.db)
docker compose run --rm crawler --get-all

# JSON e imagens em pastas customizadas
docker compose run --rm crawler --list pokemon_names.txt --json output/saida.json --images output/img
```

**Executar os testes no Docker:**

```bash
docker compose run --rm --entrypoint="" crawler python -m pytest tests/ -v
```

**Build manual da imagem (opcional):**

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

**Todos os Pokémon da National Pokédex:**

Extrai a lista da [página oficial](https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_by_National_Pok%C3%A9dex_number), processa com até 5 requisições em paralelo e salva em `todos_pokemons.json` e `todos_pokemons.db`.

```bash
python main.py --get-all
```

**Opções:**

| Argumento | Descrição | Default |
|-----------|------------|---------|
| `NOMES` | Nomes dos Pokémon (posicional) | — |
| `--list` / `-l FILE` | Arquivo com um nome por linha | — |
| `--get-all` | Extrair todos da National Pokédex (salva em `todos_pokemons.json` / `todos_pokemons.db`, máx. 5 em paralelo) | — |
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

### 3. Testes e lint (rodar local antes de enviar)

```bash
# Lint (mesmo que o CI)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Todos os testes
python -m pytest tests/ -v

# Só os testes do parser
python -m pytest tests/test_parser.py -v

# Com cobertura (opcional: pip install pytest-cov)
python -m pytest tests/ -v --cov=crawler
```

No Windows, use `py -m pytest` se `python` não estiver no PATH.

### 4. Saída

- **JSON**: arquivo com array de objetos (um por Pokémon), com todos os campos e caminho da imagem. Com `--get-all`, o arquivo gerado é `todos_pokemons.json`.
- **SQLite**: tabela `pokemon` com os mesmos dados; habilidades em JSON na coluna `abilities`. Com `--get-all`, o arquivo gerado é `todos_pokemons.db`.
- **Imagens**: arquivos em `images/` (ou no diretório indicado por `--images`), com nome derivado do Pokémon (ex.: `Bulbasaur.png`).

## Decisões técnicas

Nesta seção estão as principais escolhas de arquitetura e bibliotecas usadas no projeto, pensando em desempenho, organização do código e facilidade de manutenção.

- **HTTP (httpx)**: cliente moderno, com suporte a modo síncrono e assíncrono na mesma API, além de timeouts e redirects nativos. Ideal para crawlers sem travar o processamento.

- **Retries (tenacity)**: responsável por refazer requisições automaticamente em casos de falha de rede ou timeout, usando backoff exponencial para evitar sobrecarga.

- **Clientes persistentes**: uso de uma única instância de `AsyncClient`/`Client` durante toda a execução, aproveitando conexões reutilizáveis (keep-alive) e reduzindo overhead.

- **Parsing (BeautifulSoup)**: tolerante a HTML inconsistente da wiki e menos dependente de estruturas fixas ou XPath frágeis. Também torna o código mais legível, expressivo e fácil de manter.

- **Modelos (Pydantic)**: usado para validação e serialização dos dados, garantindo consistência tanto na exportação para JSON quanto no armazenamento em SQLite. E garantindo um dos requisitos do desafio de crawler.

- **Concorrência (asyncio)**: execução assíncrona com controle de paralelismo, permitindo várias requisições ao mesmo tempo, usando melhor o I/O sem sobrecarregar o servidor.

- **Tratamento de erros (FetchError)**: encapsula as exceções do `httpx`, evitando acoplamento direto com a biblioteca HTTP e simplificando o tratamento no restante do código.

- **Arquitetura (DDD)**: domínio em `crawler/domain/` (modelos, serviços como `storage`, exceções); camada de aplicação com requisição (`client`), extração (`parser`) e download (`downloader`); orquestração em `main.py`. Separação clara de responsabilidades e manutenção do núcleo de negócio no domínio.