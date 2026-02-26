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

## Decisões técnicas

Nesta seção estão as principais escolhas de arquitetura e bibliotecas usadas no projeto, pensando em desempenho, organização do código e facilidade de manutenção.

- **HTTP (httpx)**: cliente moderno, com suporte a modo síncrono e assíncrono na mesma API, além de timeouts e redirects nativos. Ideal para crawlers sem travar o processamento.

- **Retries (tenacity)**: responsável por refazer requisições automaticamente em casos de falha de rede ou timeout, usando backoff exponencial para evitar sobrecarga.

- **Clientes persistentes**: uso de uma única instância de `AsyncClient`/`Client` durante toda a execução, aproveitando conexões reutilizáveis (keep-alive) e reduzindo overhead.

- **Parsing (BeautifulSoup)**: tolerante a HTML inconsistente da wiki e menos dependente de estruturas fixas ou XPath frágeis. Também torna o código mais legível, expressivo e fácil de manter.

- **Modelos (Pydantic)**: usado para validação e serialização dos dados, garantindo consistência tanto na exportação para JSON quanto no armazenamento em SQLite. E garantindo um dos requisitos do desafio de crawler.

- **Concorrência (asyncio)**: execução assíncrona com controle de paralelismo, permitindo várias requisições ao mesmo tempo, usando melhor o I/O sem sobrecarregar o servidor.

- **Tratamento de erros (FetchError)**: encapsula as exceções do `httpx`, evitando acoplamento direto com a biblioteca HTTP e simplificando o tratamento no restante do código.

- **Arquitetura modular**: separação clara entre requisição (`client`), extração (`parser`), modelos (`models`), armazenamento (`storage`) e download (`downloader`), com a orquestração centralizada no `main.py`. Reflete organização e separação de responsabilidades no projeto.