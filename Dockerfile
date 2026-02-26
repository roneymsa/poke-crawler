# Poké-Crawler: extrai dados de Pokémon da Bulbapedia
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY crawler/ ./crawler/
COPY tests/ ./tests/

ENTRYPOINT ["python", "main.py"]
CMD ["--list", "pokemon_names.txt"]
