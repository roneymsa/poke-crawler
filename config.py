"""
Configuração do crawler distribuído (cron jobs).
Usado por --sync-links e --worker.
"""

# Quantos Pokémon processar por execução do worker (6 runs/dia a cada 4h)
BATCH_SIZE = 100

# Delay entre requisições (segundos) — anti-ban
DELAY_MIN = 2
DELAY_MAX = 6

# Tentativas máximas antes de marcar como failed
MAX_RETRIES = 3
